"""Upcoming catalogs jump the Equibase queue.

When a catalog is published (a new or changed upcoming_catalogs entry, from
``load_railway.py --only catalogs`` or anything else), the scrape loop pauses
its own queue and works through that catalog's hips first, in book / session /
hip order, then resumes. The site never waits: hips show "updating" until done.

Per hip the horses that matter are
  * the sire, and the covering sire of an in-foal mare,
  * the dam (narrowed by SIRE OF DAM and a foal-year window from the hip),
  * the hip itself when it is named (broodmares, prospects, stallions).
Each needs a race_horses row (Equibase profile) and a complete 5-generation
tree, which gives the hip at least 6 generations. Only horses missing either
are scraped; a named racing prospect whose record is over 30 days old is
re-opened.

Tables
  crossr_catalog_hips  per hip: status updating | complete | partial | not_found,
                       the checks behind it, and a row hash so a re-upload only
                       re-queues new or changed hips
  crossr_catalog_jobs  per catalog: queued | running | complete, counts, times.
                       status = 'complete' is the "catalog complete" signal; a
                       crossr_pipeline_runs row (job 'catalog:<id>') is written too.

Produce records: Equibase's free profiles do not list a mare's foals (that is
Equineline's paid product), so "produce" here counts the dam's foals we know
from race_horses and sales_lots; it is reported, not required.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crossr_pipeline import notify, sales_parents, state
from equibase_scraper.pedigree_fill import covers_remaining, lookup_ancestor
from equibase_scraper.queue import clean_name

SCHEMA = """
CREATE TABLE IF NOT EXISTS crossr_catalog_jobs (
    catalog_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    hips_total INTEGER NOT NULL DEFAULT 0,
    hips_to_scrape INTEGER NOT NULL DEFAULT 0,
    hips_done INTEGER NOT NULL DEFAULT 0,
    page_loads INTEGER NOT NULL DEFAULT 0,
    queued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    detail TEXT
);
CREATE TABLE IF NOT EXISTS crossr_catalog_hips (
    catalog_id TEXT NOT NULL,
    hip TEXT NOT NULL,
    row_hash TEXT NOT NULL,
    book INTEGER,
    session INTEGER,
    hip_no INTEGER,
    status TEXT NOT NULL,
    pedigree_ok BOOLEAN,
    dam_record_ok BOOLEAN,
    horse_record_ok BOOLEAN,
    dam_known_foals INTEGER,
    detail TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (catalog_id, hip)
);
CREATE INDEX IF NOT EXISTS idx_crossr_catalog_hips_status ON crossr_catalog_hips (catalog_id, status);
"""

# The names the sales-model hip pages read. Views, so there is one source of
# truth; 'partial' (scraped, but an ancestor is not on Equibase) reads as
# 'not_found'. Skipped if someone created real tables with these names.
VIEWS = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'upcoming_hip_status') THEN
        EXECUTE 'CREATE OR REPLACE VIEW upcoming_hip_status AS
                 SELECT catalog_id, hip,
                        CASE status WHEN ''partial'' THEN ''not_found'' ELSE status END AS status,
                        updated_at
                 FROM crossr_catalog_hips';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'upcoming_catalog_status') THEN
        EXECUTE 'CREATE OR REPLACE VIEW upcoming_catalog_status AS
                 SELECT catalog_id, status = ''complete'' AS complete,
                        COALESCE(completed_at, started_at, queued_at) AS updated_at
                 FROM crossr_catalog_jobs';
    END IF;
END $$;
"""

PRECOMPUTE = Path(__file__).resolve().parents[1] / "scripts" / "precompute_catalogs.py"
PRECOMPUTE_EVERY = 50
_precompute_proc = None


def precompute(*args: str) -> None:
    """Start the sales-model hip precompute in the background (one at a time).

    The scraper never waits for it; skipped while one is still running or
    before scripts/precompute_catalogs.py exists.
    """
    global _precompute_proc
    if not PRECOMPUTE.exists():
        return
    if _precompute_proc is not None and _precompute_proc.poll() is None:
        return
    log = (PRECOMPUTE.parents[1] / "logs" / "pipeline" / "precompute.log").open("a")
    _precompute_proc = subprocess.Popen(
        [sys.executable, str(PRECOMPUTE), *args], cwd=str(PRECOMPUTE.parents[1]), stdout=log, stderr=log,
    )
    print(f"precompute started: {' '.join(args)}", flush=True)

HASH_FIELDS = ("HIP", "NAME", "SEX", "SIRE", "DAM", "SIRE OF DAM", "YEAR OF BIRTH", "COVERING SIRE",
               "SOLD AS DESCRIPTION")
STALE_DAYS = 30
CHECK_EVERY_S = 300
PUSH_EVERY_S = 30 * 60  # catalog work reaches Postgres (and the site) at least this often
JOB_ITEMS = "catalog-items"


# ---------------------------------------------------------------------------
# rows -> hips -> horses (pure, tested)
# ---------------------------------------------------------------------------

def _int(value) -> int | None:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else None


def foal_year(row: dict) -> int | None:
    match = re.search(r"(19|20)\d{2}", str(row.get("YEAR OF BIRTH") or ""))
    return int(match.group(0)) if match else None


def row_hash(row: dict) -> str:
    text = json.dumps([str(row.get(k) or "").strip().upper() for k in HASH_FIELDS])
    return hashlib.sha1(text.encode()).hexdigest()


def is_named(name: str) -> bool:
    name = (name or "").strip()
    return bool(name) and not re.match(r"^(hip\b|\d{4}-)", name, re.I) and " x " not in name.lower()


def hip_horses(row: dict) -> list[dict]:
    """The horses a hip depends on, as sales_parents-style items."""
    year = foal_year(row)
    items = []

    def add(role: str, name: str, sire: str = "", window=None, part: str = ""):
        name = (name or "").strip()
        key = clean_name(name)
        if not key:
            return
        sire_key = clean_name(sire) if sire else ""
        items.append({
            "role": role, "name": name, "name_key": key, "sire": sire.strip(),
            "key": sales_parents.item_key(role, key, sire_key), "yob_range": window,
            "latest": None, "lots": 0, "part": part,
        })

    add("sire", row.get("SIRE"), part="sire")
    add("dam", row.get("DAM"), row.get("SIRE OF DAM") or "",
        (year - 25, year - 3) if year else None, part="dam")
    if (row.get("COVERING SIRE") or "").strip():
        add("sire", row.get("COVERING SIRE"), part="cover")
    sale = re.search(r"\((\d{4})\)", str(row.get("SALE TITLE") or ""))
    sale_year = int(sale.group(1)) if sale else datetime.now().year
    # Weanlings and yearlings have no race record yet; their pedigree is the
    # sire's and dam's, so only older named horses are looked up themselves.
    if is_named(row.get("NAME") or "") and not (year and year >= sale_year - 1):
        sex = (row.get("SEX") or "").strip().upper()
        add("sire" if sex in ("H", "C", "R") else "dam", row.get("NAME"), row.get("SIRE") or "",
            (year, year) if year else None, part="horse")
    return items


def sort_key(row: dict) -> tuple:
    return (_int(row.get("BOOK")) or 99, _int(row.get("SESSION")) or 99, _int(row.get("HIP")) or 0)


# ---------------------------------------------------------------------------
# assessment from the database (no page loads)
# ---------------------------------------------------------------------------

class Assessor:
    """``db`` is pgdb or the local stage, ``conn`` its connection."""

    def __init__(self, db, conn, index: dict, names: set[str]):
        self.index = index
        self.rows: dict[str, list[dict]] = {}
        for row in db.rows_by_name_keys(conn, names):
            self.rows.setdefault(row["name_key"], []).append(row)

    def horse(self, item: dict) -> dict:
        row, _why = sales_parents.pick_row(self.rows.get(item["name_key"], []), item)
        year = (row or {}).get("foal_year") or None
        tree = lookup_ancestor(self.index, item["name"], year)
        tree_ok = bool(tree) and covers_remaining(tree, 0)
        record_ok = bool(row) and row.get("status") == "ok"
        stale = False
        if record_ok and item["part"] == "horse" and row.get("fetched_at"):
            try:
                fetched = datetime.fromisoformat(row["fetched_at"].replace("Z", "+00:00"))
                stale = datetime.now(timezone.utc) - fetched > timedelta(days=STALE_DAYS)
            except ValueError:
                stale = True
        return {"row": row, "tree_ok": tree_ok, "record_ok": record_ok, "stale": stale,
                "terminal": bool(row) and row.get("status") in sales_parents.DONE - {"complete"}}


def assess_hip(assessor: Assessor, row: dict) -> dict:
    checks = {item["part"]: assessor.horse(item) for item in hip_horses(row)}
    named = "horse" in checks
    if named:
        pedigree_ok = checks["horse"]["tree_ok"]
    else:
        pedigree_ok = all(checks.get(p, {}).get("tree_ok") for p in ("sire", "dam"))
    dam_record_ok = checks.get("dam", {}).get("record_ok", False)
    horse_record_ok = checks["horse"]["record_ok"] if named else None
    needs = [p for p, c in checks.items() if not (c["tree_ok"] and c["record_ok"]) or c["stale"]]
    if not needs:
        status = "complete"
    elif all(checks[p]["terminal"] for p in needs):
        status = "not_found"
    else:
        status = "updating"
    return {"status": status, "pedigree_ok": pedigree_ok, "dam_record_ok": dam_record_ok,
            "horse_record_ok": horse_record_ok, "needs": needs, "checks": checks}


# ---------------------------------------------------------------------------
# sync: catalogs -> hips -> job
# ---------------------------------------------------------------------------

def ensure(conn) -> None:
    state.ensure(conn)
    conn.execute(SCHEMA)
    conn.execute(VIEWS)


def catalog_rows(conn, catalog_id: str, local=None) -> list[dict]:
    """A catalog's rows. With ``local`` (the stage), read from Postgres only
    when the catalog's updated_at has changed since the last read."""
    def read():
        return [r["data"] for r in conn.execute(
            "SELECT data FROM upcoming_catalog_rows WHERE catalog_id = %s ORDER BY row_no", (catalog_id,)
        )]

    if local is None:
        return read()
    from crossr_pipeline import stage

    version = conn.execute("SELECT updated_at::text AS v FROM upcoming_catalogs WHERE id = %s",
                           (catalog_id,)).fetchone()
    return stage.cached(local, f"catalog_rows:{catalog_id}", version["v"] if version else "", read)


def sync(conn, local=None) -> list[str]:
    """Queue new or changed hips of every upcoming catalog. Returns catalogs with work.

    With ``local``, a catalog whose updated_at is the one already synced is
    skipped without reading its rows (the check runs every few minutes).
    """
    ensure(conn)
    queued = []
    for cat in conn.execute("SELECT id, updated_at::text AS v FROM upcoming_catalogs WHERE source = 'upcoming' "
                            "ORDER BY id").fetchall():
        cid = cat["id"]
        if local is not None:
            from crossr_pipeline import stage

            if stage.meta_get(local, f"catalog_synced:{cid}") == cat["v"]:
                continue
        rows = catalog_rows(conn, cid, local)
        known = {r["hip"]: r["row_hash"] for r in conn.execute(
            "SELECT hip, row_hash FROM crossr_catalog_hips WHERE catalog_id = %s", (cid,))}
        current = {}
        changed = []
        for row in rows:
            hip = str(row.get("HIP") or "").strip()
            if not hip:
                continue
            digest = row_hash(row)
            current[hip] = digest
            if known.get(hip) != digest:
                book, session, hip_no = sort_key(row)
                changed.append((cid, hip, digest, book, session, hip_no))
        gone = set(known) - set(current)
        if local is not None:
            stage.meta_set(local, f"catalog_synced:{cid}", cat["v"])
        if not changed and not gone:
            continue
        with conn.transaction():
            if gone:
                conn.execute("DELETE FROM crossr_catalog_hips WHERE catalog_id = %s AND hip = ANY(%s)",
                             (cid, sorted(gone)))
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO crossr_catalog_hips (catalog_id, hip, row_hash, book, session, hip_no, status) "
                    "VALUES (%s, %s, %s, %s, %s, %s, 'updating') ON CONFLICT (catalog_id, hip) DO UPDATE SET "
                    "row_hash = EXCLUDED.row_hash, book = EXCLUDED.book, session = EXCLUDED.session, "
                    "hip_no = EXCLUDED.hip_no, status = 'updating', updated_at = now()",
                    changed,
                )
            conn.execute(
                "INSERT INTO crossr_catalog_jobs (catalog_id, status, hips_total) VALUES (%s, 'queued', %s) "
                "ON CONFLICT (catalog_id) DO UPDATE SET status = 'queued', hips_total = EXCLUDED.hips_total, "
                "queued_at = now(), completed_at = NULL",
                (cid, len(current)),
            )
        print(f"catalog {cid}: {len(changed)} new/changed hips queued, {len(gone)} removed", flush=True)
        queued.append(cid)
        precompute(cid)  # stale hips of the new or changed catalog
    for row in conn.execute("SELECT catalog_id FROM crossr_catalog_jobs WHERE status IN ('queued', 'running')"):
        if row["catalog_id"] not in queued:
            queued.append(row["catalog_id"])
    return queued


# ---------------------------------------------------------------------------
# run one catalog
# ---------------------------------------------------------------------------

def _dam_known_foals(db, conn, rows: list[dict]) -> dict[str, int]:
    dams = sorted({clean_name(r.get("DAM") or "") for r in rows} - {""})
    counts: Counter = Counter()
    for row in db.ok_dam_counts(conn, dams):
        counts[clean_name(row["dam"])] += row["n"]
    return counts


def _hip_values(cid: str, hip: str, result: dict, foals: int, detail: str = "") -> tuple:
    return (result["status"], result["pedigree_ok"], result["dam_record_ok"], result["horse_record_ok"],
            foals, (detail or ", ".join(result["needs"]))[:500], cid, hip)


def _write_hips(conn, values: list[tuple]) -> None:
    if not values:
        return
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE crossr_catalog_hips SET status = %s, pedigree_ok = %s, dam_record_ok = %s, horse_record_ok = %s, "
            "dam_known_foals = %s, detail = %s, updated_at = now() WHERE catalog_id = %s AND hip = %s",
            values,
        )


class _HipWriter:
    """Hip statuses wait until the data behind them is pushed: every
    PUSH_EVERY_S the stage is pushed, then the waiting statuses are written."""

    def __init__(self, conn, local):
        self.conn, self.local = conn, local
        self.waiting: list[tuple] = []
        self.last = time.monotonic()

    def add(self, values: tuple) -> None:
        self.waiting.append(values)
        if time.monotonic() - self.last >= PUSH_EVERY_S:
            self.flush()

    def flush(self) -> None:
        from crossr_pipeline import stage

        if self.local is not None:
            stage.push(self.local, self.conn)
        _write_hips(self.conn, self.waiting)
        self.waiting = []
        self.last = time.monotonic()


def run_catalog(eb, page, conn, book, delay: float, cid: str, limit: int | None = None, local=None,
                budget_s: float | None = None) -> dict:
    """Scrape what a catalog's queued hips are missing, in book/session/hip order.

    ``conn`` is Postgres (catalog tables); ``local`` the stage that the scraper
    reads and writes (Postgres itself when None). Stops after ``budget_s``.
    """
    from crossr_pipeline import scrape, stage

    db, data = (stage, local) if local is not None else (eb.db, conn)
    ensure(conn)
    rows = {str(r.get("HIP") or "").strip(): r for r in catalog_rows(conn, cid, local)}
    todo = [r["hip"] for r in conn.execute(
        "SELECT hip FROM crossr_catalog_hips WHERE catalog_id = %s AND status = 'updating' "
        "ORDER BY book NULLS LAST, session NULLS LAST, hip_no", (cid,))]
    foals = _dam_known_foals(db, data, [rows[h] for h in todo if h in rows])

    # First pass, no page loads: settle every hip the database already covers,
    # so only real work stays "updating".
    assessor = Assessor(db, data, book.index, {i["name_key"] for h in todo if h in rows for i in hip_horses(rows[h])})
    need = []
    settled = Counter()
    first = []
    for hip in todo:
        if hip not in rows:
            continue
        result = assess_hip(assessor, rows[hip])
        if result["status"] == "updating":
            need.append(hip)
        else:
            first.append(_hip_values(cid, hip, result, foals.get(clean_name(rows[hip].get("DAM") or ""), 0)))
            settled[result["status"]] += 1
    writer = _HipWriter(conn, local)
    writer.waiting = first
    writer.flush()
    conn.execute("UPDATE crossr_catalog_jobs SET hips_to_scrape = %s WHERE catalog_id = %s", (len(need), cid))
    print(f"catalog {cid}: {len(todo)} hips checked, {dict(settled)} already settled, {len(need)} to scrape", flush=True)
    todo = need[:limit] if limit else need

    loads = {"n": 0}
    real_wait = eb.polite_wait

    def counting_wait(pg, d):
        loads["n"] += 1
        real_wait(pg, d)

    eb.polite_wait = counting_wait
    run = state.Run(conn, f"catalog:{cid}")
    conn.execute("UPDATE crossr_catalog_jobs SET status = 'running', started_at = COALESCE(started_at, now()) "
                 "WHERE catalog_id = %s", (cid,))
    started = time.monotonic()
    done_items: dict[str, tuple[str, str]] = {}
    hips_scraped = 0
    worked = 0
    try:
        for n, hip in enumerate(todo, start=1):
            if budget_s is not None and time.monotonic() - started >= budget_s:
                print(f"catalog {cid}: batch time is up after {n - 1} hips", flush=True)
                break
            worked = n
            row = rows.get(hip)
            if row is None:
                continue
            before = assess_hip(Assessor(db, data, book.index, {i["name_key"] for i in hip_horses(row)}), row)
            if before["status"] == "complete":
                writer.add(_hip_values(cid, hip, before, foals.get(clean_name(row.get("DAM") or ""), 0)))
                run.bump("already complete")
                continue
            hips_scraped += 1
            loads_before = loads["n"]
            for item in hip_horses(row):
                if item["part"] not in before["needs"] or item["key"] in done_items:
                    continue
                check = before["checks"][item["part"]]
                if check["stale"] and check["row"] and check["row"].get("profile_url"):
                    result = scrape._with_block_retry(
                        eb, page, run, dict(check["row"]),
                        lambda: scrape.refresh_one(eb, page, data, dict(check["row"]), delay))
                    done_items[item["key"]] = (result, "refreshed")
                    continue
                try:
                    done_items[item["key"]] = scrape._with_block_retry(
                        eb, page, run, {"display_name": item["name"], "pedigree_key": item["name_key"]},
                        lambda: scrape.process_item(eb, page, data, book, item, delay))
                except Exception as exc:
                    done_items[item["key"]] = ("error", f"{exc.__class__.__name__}: {exc}"[:200])
                (stage if local is not None else state).mark_item(data, JOB_ITEMS, item["key"], *done_items[item["key"]])
            after = assess_hip(Assessor(db, data, book.index, {i["name_key"] for i in hip_horses(row)}), row)
            if after["status"] == "updating":
                results = [done_items.get(i["key"], ("", ""))[0] for i in hip_horses(row) if i["part"] in after["needs"]]
                after["status"] = "not_found" if any(r in ("not_found", "ambiguous", "year_mismatch") for r in results) else "partial"
            writer.add(_hip_values(cid, hip, after, foals.get(clean_name(row.get("DAM") or ""), 0)))
            run.bump(f"hips {after['status']}")
            run.bump("page loads", loads["n"] - loads_before)
            print(f"[catalog {n}/{len(todo)}] hip {hip}: {before['status']} -> {after['status']} "
                  f"({loads['n'] - loads_before} pages)", flush=True)
            if hips_scraped and hips_scraped % PRECOMPUTE_EVERY == 0:
                precompute("--rescraped", cid)
            if n % 10 == 0:
                run.heartbeat("running")
                conn.execute("UPDATE crossr_catalog_jobs SET hips_done = %s, page_loads = %s "
                             "WHERE catalog_id = %s", (n, loads["n"], cid))
    except BaseException as exc:
        run.finish("partial", f"stopped: {exc}")
        writer.flush()
        conn.execute("UPDATE crossr_catalog_jobs SET status = 'queued', page_loads = %s "
                     "WHERE catalog_id = %s", (loads["n"], cid))
        raise
    finally:
        eb.polite_wait = real_wait
    writer.flush()
    left = conn.execute("SELECT count(*) AS n FROM crossr_catalog_hips WHERE catalog_id = %s AND status = 'updating'",
                        (cid,)).fetchone()["n"]
    minutes = (time.monotonic() - started) / 60
    status = "complete" if left == 0 else "queued"
    conn.execute(
        "UPDATE crossr_catalog_jobs SET status = %s, hips_done = hips_done + %s, "
        "page_loads = %s, completed_at = CASE WHEN %s = 'complete' THEN now() END, detail = %s WHERE catalog_id = %s",
        (status, worked, loads["n"], status,
         f"{hips_scraped} of {worked} hips scraped, {loads['n']} pages, {minutes:.0f} min", cid),
    )
    run.finish("ok" if status == "complete" else "partial", f"{hips_scraped} hips scraped in {minutes:.0f} min")
    if status == "complete":
        notify.send("Catalog complete", f"{cid}: data filled for every hip")
        precompute("--full", cid)
    elif hips_scraped:
        precompute("--rescraped", cid)
    return {"checked": worked, "scraped": hips_scraped, "page_loads": loads["n"], "minutes": round(minutes, 1),
            "left": left}


class Hook:
    """Called between items of the normal queue; runs queued catalogs first.

    ``deadline`` (time.monotonic) ends catalog work with the batch; ``left``
    then counts hips still waiting, so the caller can start the next batch.
    """

    def __init__(self, eb, page, conn, book, delay: float, limit: int | None = None, local=None,
                 deadline: float | None = None):
        self.args = (eb, page, conn, book, delay)
        self.limit = limit
        self.local = local
        self.deadline = deadline
        self.last = 0.0
        self.left = 0

    def __call__(self, force: bool = False) -> None:
        if not force and time.monotonic() - self.last < CHECK_EVERY_S:
            return
        self.last = time.monotonic()
        eb, page, conn, book, delay = self.args
        self.left = 0
        for cid in sync(conn, self.local):
            budget = None if self.deadline is None else self.deadline - time.monotonic()
            if budget is not None and budget <= 0:
                self.left += 1
                continue
            print(f"Pausing the queue for catalog {cid}", flush=True)
            result = run_catalog(eb, page, conn, book, delay, cid, self.limit, local=self.local, budget_s=budget)
            print(result, flush=True)
            self.left += result["left"]


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def report(conn, cid: str, book_index: dict | None = None) -> dict:
    """Completeness of every hip, assessed now from the database."""
    if book_index is None:
        from equibase_scraper import pgdb
        from equibase_scraper.pedigree_fill import build_ancestor_index

        book_index = build_ancestor_index(pgdb.load_pedigree_map(conn))
    from equibase_scraper import pgdb

    rows = catalog_rows(conn, cid)
    names = {i["name_key"] for r in rows for i in hip_horses(r)}
    assessor = Assessor(pgdb, conn, book_index, names)
    foals = _dam_known_foals(pgdb, conn, rows)
    out = Counter()
    incomplete = []
    for row in rows:
        result = assess_hip(assessor, row)
        out["hips"] += 1
        out["pedigree complete"] += bool(result["pedigree_ok"])
        out["dam race record"] += bool(result["dam_record_ok"])
        if result["horse_record_ok"] is not None:
            out["named hips"] += 1
            out["named hip race record"] += bool(result["horse_record_ok"])
        out["dam has known foals"] += foals.get(clean_name(row.get("DAM") or ""), 0) > 0
        out[f"status {result['status']}"] += 1
        if result["status"] != "complete":
            incomplete.append((str(row.get("HIP")), row.get("NAME") or f"{row.get('SIRE')} x {row.get('DAM')}",
                               ", ".join(result["needs"])))
    return {"counts": dict(out), "incomplete": incomplete}

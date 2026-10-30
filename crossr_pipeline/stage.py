"""Local staging store: the pipeline reads and writes a SQLite file on the Mac
and talks to Railway once per batch, not once per horse.

state/stage.sqlite holds
  race_horses        a copy of the Postgres table (pulled once, re-pulled only
                     when someone else changes it); new and changed rows are
                     marked _dirty
  race_*_stage       seasons / starts of re-scraped horses, waiting for a push
  pedigrees          a copy of the trees (pulled by updated_at), _dirty marks new ones
  queue              crossr_pipeline_queue states; _dirty marks new attempts
  rp_fees_stage, stud_fee_stage   Racing Post results waiting for a push
  cache              derived inputs keyed by a Postgres version (sale parents,
                     catalog rows), so they are not re-read every batch
  meta               versions seen, reserved race_horses ids

``push(local, pg)`` sends everything dirty in one Postgres transaction (COPY into
TEMP tables, then set-based upserts; see crossr_core/pg_push.py) and bumps crossr_table_versions
once, so the API reloads once per push. ``prepare(local, pg)`` pushes leftovers,
pulls what changed and reserves ids; every job calls it first.

The module also implements equibase_scraper's db API (find_horses, save_profile,
mark_status, ...) on the local file, so ``run.db = stage`` points the scraper here.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from crossr_core import pg_push

REPO = Path(__file__).resolve().parents[1]
STAGE_PATH = Path(os.environ.get("CROSSR_STAGE", REPO / "state" / "stage.sqlite"))
DB_PATH = STAGE_PATH  # run.py prints DB_PATH.name

HORSE_COLS = [
    "id", "pedigree_key", "name_key", "foal_year", "display_name", "foaled_in", "breed", "color", "sex",
    "foaled", "sire", "sire_refno", "dam", "dam_refno", "damsire", "damsire_refno", "jockey", "trainer",
    "owner", "breeder", "best_class", "equibase_refno", "registry", "profile_url", "status", "detail",
    "fetched_at", "queue_batch",
]
SEASON_FIELDS = ["year", "starts", "firsts", "seconds", "thirds", "highest_esf", "earnings", "earnings_per_start"]
START_FIELDS = ["race_date", "track", "track_code", "country", "race_number", "race_name", "grade", "breed",
                "place", "esf", "stakes_id", "chart_url", "video_url"]
PROFILE_FIELDS = [
    "foaled_in", "breed", "color", "sex", "foaled", "sire", "sire_refno", "dam", "dam_refno", "damsire",
    "damsire_refno", "jockey", "trainer", "owner", "breeder", "best_class", "equibase_refno", "registry",
    "profile_url",
]
RP_COLS = ["stallion_key", "stallion", "rp_horse_id", "rp_name", "year", "stud_fee", "currency", "is_private",
           "country", "standing"]
FEE_COLS = ["Year", "Stallion", "Stud Fee", "Farm", "Source List", "Notes"]

HORSES_SEQ = "crossr_race_horses_id_seq"
ID_BLOCK = 50_000
ID_LOW_WATER = 20_000

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS race_horses (
    {", ".join(f"{c} TEXT" + (" PRIMARY KEY" if c == "id" else "") for c in HORSE_COLS)},
    _dirty INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS l_horses_key ON race_horses (pedigree_key);
CREATE INDEX IF NOT EXISTS l_horses_name_year ON race_horses (name_key, foal_year);
CREATE INDEX IF NOT EXISTS l_horses_refno ON race_horses (equibase_refno);
CREATE INDEX IF NOT EXISTS l_horses_status ON race_horses (status);
CREATE INDEX IF NOT EXISTS l_horses_dam ON race_horses (upper(dam));
CREATE INDEX IF NOT EXISTS l_horses_dirty ON race_horses (_dirty) WHERE _dirty > 0;

CREATE TABLE IF NOT EXISTS race_seasons_stage (horse_id TEXT NOT NULL, {", ".join(f"{c} TEXT" for c in SEASON_FIELDS)});
CREATE INDEX IF NOT EXISTS l_seasons_horse ON race_seasons_stage (horse_id);
CREATE TABLE IF NOT EXISTS race_starts_stage (horse_id TEXT NOT NULL, {", ".join(f"{c} TEXT" for c in START_FIELDS)});
CREATE INDEX IF NOT EXISTS l_starts_horse ON race_starts_stage (horse_id);
CREATE TABLE IF NOT EXISTS stage_children (horse_id TEXT PRIMARY KEY);

CREATE TABLE IF NOT EXISTS pedigrees (
    key TEXT PRIMARY KEY, tree TEXT NOT NULL, updated_at TEXT, _dirty INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS l_pedigrees_dirty ON pedigrees (_dirty) WHERE _dirty > 0;

CREATE TABLE IF NOT EXISTS queue (
    job TEXT NOT NULL, item_key TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
    last_attempt TEXT NOT NULL, detail TEXT, _dirty INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (job, item_key)
);

CREATE TABLE IF NOT EXISTS rp_fees_stage (rp_horse_id TEXT NOT NULL, row TEXT);
CREATE TABLE IF NOT EXISTS stud_fee_stage (row TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, version TEXT, value TEXT);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


def _dict_row(cursor, row):
    return {d[0]: v for d, v in zip(cursor.description, row)}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cell(value):
    if value is None:
        return None
    text = str(value)
    return text if text.strip() != "" else None


def connect(path: Path | None = None) -> sqlite3.Connection:
    dest = Path(path or STAGE_PATH)
    dest.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(dest, timeout=300, isolation_level=None)
    conn.row_factory = _dict_row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 300000")
    conn.executescript(SCHEMA)
    return conn


def meta_get(conn, key: str, default=None):
    row = conn.execute("SELECT v FROM meta WHERE k = ?", (key,)).fetchone()
    return row["v"] if row else default


def meta_set(conn, key: str, value) -> None:
    conn.execute("INSERT INTO meta (k, v) VALUES (?, ?) ON CONFLICT (k) DO UPDATE SET v = excluded.v",
                 (key, None if value is None else str(value)))


# ---------------------------------------------------------------------------
# cache: derived inputs keyed by a version string
# ---------------------------------------------------------------------------

def cached(conn, key: str, version: str, build):
    """``build()`` once per ``version``; the JSON result lives in the cache table."""
    row = conn.execute("SELECT version, value FROM cache WHERE k = ?", (key,)).fetchone()
    if row and row["version"] == version:
        return json.loads(row["value"])
    value = build()
    conn.execute("INSERT INTO cache (k, version, value) VALUES (?, ?, ?) ON CONFLICT (k) DO UPDATE SET "
                 "version = excluded.version, value = excluded.value", (key, version, json.dumps(value)))
    return value


# ---------------------------------------------------------------------------
# queue states (crossr_pipeline_queue, kept here between pushes)
# ---------------------------------------------------------------------------

def queue_states(conn, job: str) -> dict[str, dict]:
    out = {}
    for row in conn.execute("SELECT item_key, status, attempts, last_attempt FROM queue WHERE job = ?", (job,)):
        row["last_attempt"] = datetime.fromisoformat(row["last_attempt"])
        out[row["item_key"]] = row
    return out


def mark_item(conn, job: str, item_key: str, status: str, detail: str = "") -> None:
    conn.execute(
        "INSERT INTO queue (job, item_key, status, attempts, last_attempt, detail, _dirty) "
        "VALUES (?, ?, ?, 1, ?, ?, 1) ON CONFLICT (job, item_key) DO UPDATE SET "
        "status = excluded.status, attempts = queue.attempts + 1, last_attempt = excluded.last_attempt, "
        "detail = excluded.detail, _dirty = queue._dirty + 1",
        (job, item_key, status, _now(), (detail or "")[:500]),
    )


# ---------------------------------------------------------------------------
# Racing Post results, waiting for a push
# ---------------------------------------------------------------------------

def stage_racing_post(conn, rp_horse_id: str, rows: list[dict], additions: list[dict]) -> None:
    """Replace this horse's racing_post_fees rows and add stud_fees rows at the next push."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM rp_fees_stage WHERE rp_horse_id = ?", (rp_horse_id,))
        conn.executemany("INSERT INTO rp_fees_stage (rp_horse_id, row) VALUES (?, ?)",
                         [(rp_horse_id, json.dumps(r)) for r in rows] or [(rp_horse_id, None)])
        conn.executemany("INSERT INTO stud_fee_stage (row) VALUES (?)", [(json.dumps(a),) for a in additions])
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


# ---------------------------------------------------------------------------
# pull
# ---------------------------------------------------------------------------

def _dirty_count(conn) -> int:
    return sum(conn.execute(sql).fetchone()["n"] for sql in (
        "SELECT count(*) AS n FROM race_horses WHERE _dirty > 0",
        "SELECT count(*) AS n FROM pedigrees WHERE _dirty > 0",
        "SELECT count(*) AS n FROM queue WHERE _dirty > 0",
        "SELECT count(*) AS n FROM rp_fees_stage",
        "SELECT count(*) AS n FROM stud_fee_stage",
    ))


def _copy_rows(pg, sql: str, params=()):
    """Stream a query's rows with COPY (text, no per-row round trips)."""
    raw = pg.raw() if hasattr(pg, "raw") else pg
    with raw.cursor() as cur:
        with cur.copy(f"COPY ({sql}) TO STDOUT", params) as copy:
            yield from copy.rows()


def pull_horses(local, pg) -> int:
    local.execute("BEGIN IMMEDIATE")
    try:
        local.execute("DELETE FROM race_horses")
        cols = ", ".join(HORSE_COLS)
        marks = ", ".join("?" * len(HORSE_COLS))
        batch, n = [], 0
        for row in _copy_rows(pg, f"SELECT {cols} FROM race_horses"):
            batch.append(row)
            if len(batch) >= 20_000:
                local.executemany(f"INSERT OR REPLACE INTO race_horses ({cols}) VALUES ({marks})", batch)
                n += len(batch)
                batch = []
        local.executemany(f"INSERT OR REPLACE INTO race_horses ({cols}) VALUES ({marks})", batch)
        n += len(batch)
        local.execute("COMMIT")
    except BaseException:
        local.execute("ROLLBACK")
        raise
    return n


def pull_pedigrees(local, pg, full: bool = False) -> int:
    since = None if full else meta_get(local, "pedigrees_pulled_at")
    sql = "SELECT key, tree::text, updated_at::text FROM pedigrees"
    params: tuple = ()
    if since:
        sql += " WHERE updated_at > %s::timestamptz"
        params = (since,)
    local.execute("BEGIN IMMEDIATE")
    try:
        if full:
            local.execute("DELETE FROM pedigrees")
        n, latest, batch = 0, since, []
        for key, tree, updated in _copy_rows(pg, sql, params):
            batch.append((key, tree, updated))
            latest = updated if not latest or updated > latest else latest
            if len(batch) >= 5000:
                local.executemany("INSERT OR REPLACE INTO pedigrees (key, tree, updated_at, _dirty) "
                                  "VALUES (?, ?, ?, 0)", batch)
                n += len(batch)
                batch = []
        local.executemany("INSERT OR REPLACE INTO pedigrees (key, tree, updated_at, _dirty) VALUES (?, ?, ?, 0)",
                          batch)
        n += len(batch)
        if latest:
            meta_set(local, "pedigrees_pulled_at", latest)
        local.execute("COMMIT")
    except BaseException:
        local.execute("ROLLBACK")
        raise
    return n


def pull_queue(local, pg) -> int:
    rows = [(r["job"], r["item_key"], r["status"], r["attempts"], r["last_attempt"].isoformat(), r["detail"])
            for r in pg.execute("SELECT job, item_key, status, attempts, last_attempt, detail FROM crossr_pipeline_queue")]
    local.execute("BEGIN IMMEDIATE")
    try:
        local.execute("DELETE FROM queue")
        local.executemany("INSERT INTO queue (job, item_key, status, attempts, last_attempt, detail, _dirty) "
                          "VALUES (?, ?, ?, ?, ?, ?, 0)", rows)
        local.execute("COMMIT")
    except BaseException:
        local.execute("ROLLBACK")
        raise
    return len(rows)


def reserve_ids(local, pg) -> None:
    """Take a block of race_horses ids from the Postgres sequence, so rows made
    here never collide with rows made anywhere else."""
    nxt, end = int(meta_get(local, "id_next", 0)), int(meta_get(local, "id_end", -1))
    if end - nxt + 1 >= ID_LOW_WATER:
        return
    top = pg.execute(
        f"SELECT setval('{HORSES_SEQ}', GREATEST((SELECT last_value FROM {HORSES_SEQ}), "
        f"(SELECT COALESCE(MAX(id::bigint), 0) FROM race_horses WHERE id ~ '^[0-9]+$')) + %s) AS top",
        (ID_BLOCK,),
    ).fetchone()["top"]
    meta_set(local, "id_next", top - ID_BLOCK + 1)
    meta_set(local, "id_end", top)


def bind(local, pg) -> None:
    """A stage file belongs to one database: refuse to mix production and crossr_dev."""
    name = pg.execute("SELECT current_database() AS db").fetchone()["db"]
    bound = meta_get(local, "database")
    if bound is None:
        meta_set(local, "database", name)
    elif bound != name:
        raise RuntimeError(f"{STAGE_PATH} holds rows for database {bound!r}, not {name!r}. "
                           "Set CROSSR_STAGE to another file for this database.")


def prepare(local, pg, log=print, race_data: bool = True) -> dict:
    """Before a job: push leftovers, pull whatever someone else changed, reserve
    ids. race_data=False (Racing Post) skips the race_horses / pedigrees copy."""
    from equibase_scraper import pgdb

    bind(local, pg)
    out = {}
    if _dirty_count(local):
        out["pushed"] = push(local, pg, log=log)
    if not local.execute("SELECT 1 FROM queue LIMIT 1").fetchone():
        out["queue pulled"] = pull_queue(local, pg)
    if not race_data:
        return out
    pgdb.ensure_schema(pg)
    versions = pg_push.table_versions(pg, ("race_horses", "pedigrees"))
    if meta_get(local, "race_horses_version") != versions.get("race_horses") or \
            not local.execute("SELECT 1 FROM race_horses LIMIT 1").fetchone():
        started = time.monotonic()
        out["horses pulled"] = pull_horses(local, pg)
        meta_set(local, "race_horses_version", versions.get("race_horses"))
        log(f"stage: pulled {out['horses pulled']} race_horses in {time.monotonic() - started:.0f}s")
    if meta_get(local, "pedigrees_version") != versions.get("pedigrees"):
        empty = not local.execute("SELECT 1 FROM pedigrees LIMIT 1").fetchone()
        out["pedigrees pulled"] = pull_pedigrees(local, pg, full=empty)
        pg_count = pg.execute("SELECT count(*) AS n FROM pedigrees").fetchone()["n"]
        if local.execute("SELECT count(*) AS n FROM pedigrees").fetchone()["n"] != pg_count:
            out["pedigrees pulled"] = pull_pedigrees(local, pg, full=True)  # deletes or old timestamps
        meta_set(local, "pedigrees_version", versions.get("pedigrees"))
        log(f"stage: pulled {out['pedigrees pulled']} pedigrees")
    reserve_ids(local, pg)
    return out


# ---------------------------------------------------------------------------
# push
# ---------------------------------------------------------------------------

def push(local, pg, log=print) -> dict:
    """Send everything staged to Postgres in one transaction, then bump versions once."""
    from equibase_scraper import pgdb

    bind(local, pg)
    started = time.monotonic()
    local.execute("BEGIN IMMEDIATE")  # the scraper waits (busy_timeout) while a push runs
    try:
        horses = local.execute(f"SELECT {', '.join(HORSE_COLS)} FROM race_horses WHERE _dirty > 0").fetchall()
        children = [r["horse_id"] for r in local.execute("SELECT horse_id FROM stage_children")]
        seasons = local.execute("SELECT * FROM race_seasons_stage").fetchall()
        starts = local.execute("SELECT * FROM race_starts_stage").fetchall()
        peds = local.execute("SELECT key, tree FROM pedigrees WHERE _dirty > 0").fetchall()
        marks = local.execute("SELECT job, item_key, status, _dirty AS tries, last_attempt, detail "
                              "FROM queue WHERE _dirty > 0").fetchall()
        rp_rows = local.execute("SELECT rp_horse_id, row FROM rp_fees_stage").fetchall()
        fee_rows = [json.loads(r["row"]) for r in local.execute("SELECT row FROM stud_fee_stage")]
        counts: dict = {}
        changed: list[str] = []
        if any((horses, children, peds, marks, rp_rows, fee_rows)):
            with pg.transaction():
                if horses:
                    counts["race_horses"] = pg_push.upsert(pg, "race_horses", HORSE_COLS, ("id",), horses)
                    changed.append("race_horses")
                if children:
                    counts["race_seasons"] = pg_push.replace_by(
                        pg, "race_seasons", ["id", "horse_id", *SEASON_FIELDS], "horse_id", children, seasons,
                        id_seq="crossr_race_seasons_id_seq")
                    counts["race_starts"] = pg_push.replace_by(
                        pg, "race_starts", ["id", "horse_id", *START_FIELDS], "horse_id", children, starts,
                        id_seq="crossr_race_starts_id_seq")
                    changed += ["race_seasons", "race_starts"]
                if peds:
                    counts["pedigrees"] = _push_pedigrees(pg, peds)
                    changed.append("pedigrees")
                if marks:
                    counts["queue"] = _push_queue(pg, marks)
                if rp_rows:
                    rows = [json.loads(r["row"]) for r in rp_rows if r["row"]]
                    counts["racing_post_fees"] = pg_push.replace_by(
                        pg, "racing_post_fees", RP_COLS, "rp_horse_id", {r["rp_horse_id"] for r in rp_rows}, rows)
                if fee_rows:
                    counts["stud_fees"] = pg_push.upsert(pg, "stud_fees", FEE_COLS, ("Year", "Stallion", "Source List"),
                                                         fee_rows, keep_blanks=True)
                    changed.append("stud_fees")
        if changed:
            pgdb.flush_versions(pg, changed)
            versions = pg_push.table_versions(pg, ("race_horses", "pedigrees"))
            for table in ("race_horses", "pedigrees"):
                if table in changed:
                    meta_set(local, f"{table}_version", versions.get(table))
        local.execute("UPDATE race_horses SET _dirty = 0 WHERE _dirty > 0")
        local.execute("UPDATE pedigrees SET _dirty = 0 WHERE _dirty > 0")
        local.execute("UPDATE queue SET _dirty = 0 WHERE _dirty > 0")
        for table in ("stage_children", "race_seasons_stage", "race_starts_stage", "rp_fees_stage", "stud_fee_stage"):
            local.execute(f"DELETE FROM {table}")
        local.execute("COMMIT")
    except BaseException:
        local.execute("ROLLBACK")
        raise
    summary = {k: v for k, v in counts.items()}
    if summary:
        log(f"stage: pushed {summary} in {time.monotonic() - started:.1f}s; API reload: {', '.join(changed) or 'none'}")
    return summary


def _push_pedigrees(pg, rows: list[dict]) -> int:
    pg.execute("DROP TABLE IF EXISTS _push_pedigrees")
    pg.execute("CREATE TEMP TABLE _push_pedigrees (key TEXT, tree TEXT) ON COMMIT DROP")
    with pg.cursor() as cur:
        with cur.copy("COPY _push_pedigrees (key, tree) FROM STDIN") as copy:
            for r in rows:
                copy.write_row([r["key"], r["tree"]])
    return pg.execute(
        "INSERT INTO pedigrees (key, tree, updated_at) SELECT key, tree::jsonb, now() FROM _push_pedigrees "
        "ON CONFLICT (key) DO UPDATE SET tree = EXCLUDED.tree, updated_at = now()"
    ).rowcount


def _push_queue(pg, rows: list[dict]) -> int:
    pg.execute("DROP TABLE IF EXISTS _push_queue")
    pg.execute("CREATE TEMP TABLE _push_queue (job TEXT, item_key TEXT, status TEXT, tries INTEGER, "
               "last_attempt TIMESTAMPTZ, detail TEXT) ON COMMIT DROP")
    with pg.cursor() as cur:
        with cur.copy("COPY _push_queue FROM STDIN") as copy:
            for r in rows:
                copy.write_row([r["job"], r["item_key"], r["status"], r["tries"], r["last_attempt"], r["detail"]])
    return pg.execute(
        "INSERT INTO crossr_pipeline_queue (job, item_key, status, attempts, last_attempt, detail) "
        "SELECT job, item_key, status, tries, last_attempt, detail FROM _push_queue "
        "ON CONFLICT (job, item_key) DO UPDATE SET status = EXCLUDED.status, "
        "attempts = crossr_pipeline_queue.attempts + EXCLUDED.attempts, "
        "last_attempt = EXCLUDED.last_attempt, detail = EXCLUDED.detail"
    ).rowcount


def pending(local) -> dict:
    out = {}
    for label, sql in (
        ("race_horses", "SELECT count(*) AS n FROM race_horses WHERE _dirty > 0"),
        ("horses with new starts", "SELECT count(*) AS n FROM stage_children"),
        ("pedigrees", "SELECT count(*) AS n FROM pedigrees WHERE _dirty > 0"),
        ("queue marks", "SELECT count(*) AS n FROM queue WHERE _dirty > 0"),
        ("racing post horses", "SELECT count(DISTINCT rp_horse_id) AS n FROM rp_fees_stage"),
        ("stud_fees rows", "SELECT count(*) AS n FROM stud_fee_stage"),
    ):
        out[label] = local.execute(sql).fetchone()["n"]
    return out


# ---------------------------------------------------------------------------
# equibase_scraper db API on the local file (see equibase_scraper/pgdb.py)
# ---------------------------------------------------------------------------

def _next_id(conn) -> str:
    nxt, end = int(meta_get(conn, "id_next", 0)), int(meta_get(conn, "id_end", -1))
    if nxt > end:
        raise RuntimeError("No reserved race_horses ids left; run `python -m crossr_pipeline push` first")
    meta_set(conn, "id_next", nxt + 1)
    return str(nxt)


def flush_versions(conn, tables=()) -> None:
    """Versions are bumped by push(); nothing to do on the local file."""


def upsert_pending(conn, subj: dict) -> None:
    key = subj["pedigree_key"]
    params = (_cell(subj.get("name_key")), _cell(subj.get("foal_year")), _cell(subj.get("display_name")), key)
    if conn.execute("SELECT 1 FROM race_horses WHERE pedigree_key = ? LIMIT 1", (key,)).fetchone():
        conn.execute("UPDATE race_horses SET name_key = ?, foal_year = ?, display_name = ?, _dirty = 1 "
                     "WHERE pedigree_key = ? AND status IN ('pending', 'error', 'blocked')", params)
        return
    conn.execute("INSERT INTO race_horses (id, name_key, foal_year, display_name, pedigree_key, status, _dirty) "
                 "VALUES (?, ?, ?, ?, ?, 'pending', 1)", (_next_id(conn), *params))


def get_by_id(conn, horse_id) -> dict | None:
    return conn.execute("SELECT * FROM race_horses WHERE id = ?", (str(horse_id),)).fetchone()


def find_by_equibase_refno(conn, refno: str | None) -> dict | None:
    token = str(refno or "").strip()
    if not token:
        return None
    return conn.execute(
        "SELECT * FROM race_horses WHERE equibase_refno = ? "
        "ORDER BY CASE status WHEN 'ok' THEN 0 ELSE 1 END, CAST(id AS INTEGER) LIMIT 1", (token,)
    ).fetchone()


def ok_horses(conn) -> list[dict]:
    return conn.execute("SELECT * FROM race_horses WHERE status = 'ok' ORDER BY CAST(id AS INTEGER)").fetchall()


def find_horses(conn, query: str, name_key: str, year: str | None) -> list[dict]:
    year_s = str(year).strip() if year else ""
    rows = conn.execute(
        "SELECT * FROM race_horses WHERE pedigree_key = ? OR pedigree_key = ? ORDER BY foal_year, pedigree_key",
        (query.strip(), query.strip().upper()),
    ).fetchall()
    if not rows and name_key:
        if year_s:
            rows = conn.execute("SELECT * FROM race_horses WHERE name_key = ? AND foal_year = ? ORDER BY pedigree_key",
                                (name_key, year_s)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM race_horses WHERE name_key = ? ORDER BY foal_year, pedigree_key",
                                (name_key,)).fetchall()
    elif year_s:
        rows = [row for row in rows if (row["foal_year"] or "") == year_s]
    return list(rows)


def key_taken(conn, key: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM race_horses WHERE pedigree_key = ? LIMIT 1", (key,)).fetchone())


def rows_by_name_keys(conn, names) -> list[dict]:
    names = sorted(names)
    out = []
    for i in range(0, len(names), 500):
        chunk = names[i:i + 500]
        out += conn.execute(
            "SELECT id, name_key, display_name, foal_year, sire, dam, status, fetched_at, profile_url "
            f"FROM race_horses WHERE name_key IN ({', '.join('?' * len(chunk))})", chunk).fetchall()
    return out


def ok_dam_counts(conn, dams) -> list[dict]:
    dams = sorted(dams)
    out = []
    for i in range(0, len(dams), 500):
        chunk = dams[i:i + 500]
        out += conn.execute(
            "SELECT upper(dam) AS dam, count(*) AS n FROM race_horses WHERE status = 'ok' "
            f"AND upper(dam) IN ({', '.join('?' * len(chunk))}) GROUP BY 1", chunk).fetchall()
    return out


def fetched_at_by_id(conn, ids) -> dict[str, str]:
    ids = [str(i) for i in ids]
    out = {}
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        for r in conn.execute(f"SELECT id, fetched_at FROM race_horses WHERE id IN ({', '.join('?' * len(chunk))})",
                              chunk):
            out[r["id"]] = r["fetched_at"] or ""
    return out


def insert_batch_horse(conn, subj: dict) -> bool:
    if key_taken(conn, subj["pedigree_key"]):
        return False
    conn.execute(
        "INSERT INTO race_horses (id, pedigree_key, name_key, foal_year, display_name, sire, dam, sex, status, "
        "queue_batch, _dirty) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, 1)",
        (_next_id(conn), subj["pedigree_key"], _cell(subj.get("name_key")), _cell(subj.get("foal_year")),
         _cell(subj.get("display_name")), _cell(subj.get("sire")), _cell(subj.get("dam")),
         _cell(subj.get("sex")), _cell(subj.get("queue_batch"))),
    )
    return True


def resume_horses(conn, batch: str | None = None) -> list[dict]:
    if batch:
        return conn.execute("SELECT * FROM race_horses WHERE queue_batch = ? AND status IN ('pending', 'error', "
                            "'blocked') ORDER BY CAST(id AS INTEGER)", (batch,)).fetchall()
    return conn.execute("SELECT * FROM race_horses WHERE status IN ('pending', 'error', 'blocked') "
                        "ORDER BY CAST(id AS INTEGER)").fetchall()


def count_by_status(conn) -> dict[str, int]:
    return {r["status"]: r["n"] for r in conn.execute("SELECT status, count(*) AS n FROM race_horses GROUP BY status")}


def count_rows(conn) -> int:
    return conn.execute("SELECT count(*) AS n FROM race_horses").fetchone()["n"]


def mark_status(conn, horse_id, status: str, detail: str, fetched_at: str) -> None:
    conn.execute("UPDATE race_horses SET status = ?, detail = ?, fetched_at = ?, _dirty = 1 WHERE id = ?",
                 (status, _cell((detail or "")[:500]), fetched_at, str(horse_id)))


def save_profile(conn, horse_id, profile: dict, status: str, detail: str, fetched_at: str) -> None:
    """Store the profile; its seasons and starts replace the horse's at the next push."""
    horse_id = str(horse_id)
    sets = ", ".join(f"{field} = ?" for field in PROFILE_FIELDS)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            f"UPDATE race_horses SET display_name = COALESCE(?, display_name), foal_year = COALESCE(?, foal_year), "
            f"{sets}, status = ?, detail = ?, fetched_at = ?, _dirty = 1 WHERE id = ?",
            (_cell(profile.get("display_name")), _cell(profile.get("foal_year")),
             *(_cell(profile.get(f)) for f in PROFILE_FIELDS), status, _cell((detail or "")[:500]), fetched_at,
             horse_id),
        )
        conn.execute("INSERT OR IGNORE INTO stage_children (horse_id) VALUES (?)", (horse_id,))
        for table, fields, rows in (("race_seasons_stage", SEASON_FIELDS, profile.get("year_stats") or []),
                                    ("race_starts_stage", START_FIELDS, profile.get("starts") or [])):
            conn.execute(f"DELETE FROM {table} WHERE horse_id = ?", (horse_id,))
            conn.executemany(
                f"INSERT INTO {table} (horse_id, {', '.join(fields)}) VALUES (?, {', '.join('?' * len(fields))})",
                [(horse_id, *(_cell(r.get(f)) for f in fields)) for r in rows])
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def year_rows(conn, horse_id) -> list[dict]:
    """Staged seasons only (pushed ones live in Postgres)."""
    return conn.execute("SELECT * FROM race_seasons_stage WHERE horse_id = ? ORDER BY year", (str(horse_id),)).fetchall()


def start_rows(conn, horse_id) -> list[dict]:
    return conn.execute("SELECT * FROM race_starts_stage WHERE horse_id = ? ORDER BY race_date",
                        (str(horse_id),)).fetchall()


def load_pedigree_map(conn) -> dict:
    """All trees from the local copy, identical subtrees shared (see pgdb)."""
    canon: dict = {}

    def intern(node):
        out = {}
        for key, value in node.items():
            if isinstance(value, dict):
                value = intern(value)
            elif isinstance(value, str):
                value = sys.intern(value)
            out[sys.intern(key)] = value
        try:
            sig = tuple((k, id(v) if isinstance(v, dict) else v) for k, v in sorted(out.items()))
        except TypeError:
            return out
        return canon.setdefault(sig, out)

    out: dict = {}
    for row in conn.execute("SELECT key, tree FROM pedigrees"):
        tree = json.loads(row["tree"])
        out[row["key"]] = intern(tree) if isinstance(tree, dict) else tree
    return out


def upsert_pedigrees(conn, items: dict) -> int:
    if not items:
        return 0
    conn.executemany(
        "INSERT INTO pedigrees (key, tree, updated_at, _dirty) VALUES (?, ?, ?, 1) "
        "ON CONFLICT (key) DO UPDATE SET tree = excluded.tree, updated_at = excluded.updated_at, _dirty = 1",
        [(str(k), json.dumps(t), _now()) for k, t in items.items()],
    )
    return len(items)

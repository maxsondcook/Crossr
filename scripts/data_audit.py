"""Nightly data audit: catch wrong numbers, empty panels and junk labels before anyone sees them.

Read-only. Two kinds of check:

* database checks (SQL on DATABASE_URL): earnings that don't add up, race
  records older than the horse, duplicate records, sale lots without a hip;
* live-site checks (HTTP against the production API, a sample of pages):
  stallion profiles, top progeny, upcoming-sale hips and hypomating, looking
  for figures that contradict the race record, "N/A" / "undefined" labels,
  repeated grades, pedigree gaps and empty panels.

Each check has a threshold; anything over it is a FAIL. The report goes to
logs/audit/<date>.md and the data_audit_runs table, and the exit code is 1 when
anything failed, so the scheduled job's log shows it.

Usage:
    python3 scripts/data_audit.py                  # everything
    python3 scripts/data_audit.py --skip-api       # database checks only
    python3 scripts/data_audit.py --api https://api-production-f372.up.railway.app --sample 30
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

API = "https://api-production-f372.up.railway.app"
JUNK = re.compile(r"^(n/?a|#n/?a|undefined|nan|null|none|\[object object\])$", re.I)
GRADE_IN_NAME = re.compile(r"\(\s*(gr\.?|grade|g)\s*[123]\s*\)", re.I)


class Audit:
    def __init__(self):
        self.results = []

    def check(self, name: str, bad: int, total: int, examples=(), max_bad: int = 0, note: str = ""):
        ok = bad <= max_bad
        self.results.append({"check": name, "ok": ok, "bad": bad, "total": total,
                             "examples": [str(e)[:200] for e in list(examples)[:5]], "note": note})
        print(f"{'ok  ' if ok else 'FAIL'} {name}: {bad} of {total}{' - ' + note if note else ''}", flush=True)

    @property
    def failed(self):
        return [r for r in self.results if not r["ok"]]


# ----------------------------------------------------------------- database
DB_CHECKS = [
    # name, SQL returning (bad_count, total, examples array), max_bad, note
    ("career earnings = sum of seasons", """
        WITH s AS (
          SELECT horse_id,
                 max(nullif(regexp_replace(earnings::text, '[^0-9]', '', 'g'), '')::numeric) FILTER (WHERE year = 'Career') AS career,
                 sum(nullif(regexp_replace(earnings::text, '[^0-9]', '', 'g'), '')::numeric) FILTER (WHERE year ~ '^[0-9]{4}$') AS seasons
          FROM race_seasons GROUP BY horse_id)
        SELECT count(*) FILTER (WHERE career IS NOT NULL AND seasons IS NOT NULL AND abs(career - seasons) > greatest(100, 0.01 * career)),
               count(*) FILTER (WHERE career IS NOT NULL AND seasons IS NOT NULL),
               (array_agg(horse_id || ': career ' || career || ' vs seasons ' || seasons)
                  FILTER (WHERE career IS NOT NULL AND seasons IS NOT NULL AND abs(career - seasons) > greatest(100, 0.01 * career)))[1:5]
        FROM s""", 50, "small gaps are seasons the scraper hasn't refreshed"),
    ("race seasons before the horse could race", """
        SELECT count(*) FILTER (WHERE s.year::int < substring(h.foal_year from '^[0-9]{4}')::int + 2), count(*),
               (array_agg(h.display_name || ' (' || h.foal_year || ') raced ' || s.year)
                  FILTER (WHERE s.year::int < substring(h.foal_year from '^[0-9]{4}')::int + 2))[1:5]
        FROM race_seasons s JOIN race_horses h ON h.id = s.horse_id
        WHERE s.year ~ '^[0-9]{4}$' AND h.foal_year ~ '^[0-9]{4}'""", 20,
     "mostly southern-hemisphere horses, which race in the year after foaling"),
    ("duplicate Equibase IDs", """
        SELECT count(*), (SELECT count(DISTINCT equibase_refno) FROM race_horses WHERE coalesce(equibase_refno, '') <> ''),
               (array_agg(equibase_refno))[1:5]
        FROM (SELECT equibase_refno FROM race_horses WHERE coalesce(equibase_refno, '') <> ''
              AND coalesce(status, '') <> 'merged' GROUP BY 1 HAVING count(*) > 1) x""", 0, ""),
    ("exact duplicate sale lots", """
        SELECT coalesce(sum(n - 1), 0)::int, (SELECT count(*) FROM sales_lots), (array_agg(source_file || ' hip ' || hip))[1:5]
        FROM (SELECT source_file, hip, count(*) n FROM sales_lots
              GROUP BY catalog_year, catalog_title, source_file, hip, name, name_key, sex, sex_letter, sire, sire_key,
                       dam, dam_key, damsire, damsire_key, color, consignor, purchaser, barn, foaled_location,
                       birth_year, price_raw, price_num, is_rna, is_out, is_fasig
              HAVING count(*) > 1) x""", 0, "every column identical"),
    ("sale lots without a hip", """
        SELECT count(*) FILTER (WHERE coalesce(hip, '') IN ('', 'N/A')), count(*),
               (array_agg(DISTINCT source_file) FILTER (WHERE coalesce(hip, '') IN ('', 'N/A')))[1:5]
        FROM sales_lots""", 20, "a few old catalogs never had hip numbers"),
    ("stud fee jumps over 20x in a year", """
        WITH f AS (SELECT upper("Stallion") s, "Year"::int y,
                          max(nullif(regexp_replace("Stud Fee", '[^0-9]', '', 'g'), '')::numeric) fee
                   FROM stud_fees WHERE "Year" ~ '^[0-9]{4}$' AND "Stud Fee" ~ '^\\$' GROUP BY 1, 2)
        SELECT count(*) FILTER (WHERE b.fee > 20 * a.fee OR a.fee > 20 * b.fee), count(*),
               (array_agg(a.s || ' ' || a.y || ': ' || a.fee || ' -> ' || b.fee) FILTER (WHERE b.fee > 20 * a.fee OR a.fee > 20 * b.fee))[1:5]
        FROM f a JOIN f b ON b.s = a.s AND b.y = a.y + 1 WHERE a.fee > 0 AND b.fee > 0""", 5, "usually a namesake's fee or a typo"),
]


def run_db(audit: Audit) -> None:
    from crossr_core import railway_db

    with railway_db.connect() as conn:
        conn.execute("SET statement_timeout = '300s'")
        conn.execute("SET default_transaction_read_only = on")
        for name, sql, max_bad, note in DB_CHECKS:
            try:
                bad, total, ex = conn.execute(sql).fetchone()
                audit.check(name, int(bad or 0), int(total or 0), ex or [], max_bad, note)
            except Exception as exc:
                conn.rollback()
                conn.execute("SET statement_timeout = '300s'")
                audit.check(name, 1, 1, [f"{exc.__class__.__name__}: {str(exc).splitlines()[0]}"], 0, "check could not run")


# ----------------------------------------------------------------- live site
def get(api: str, path: str, body=None, timeout: int = 120):
    url = api.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "crossr-audit"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code < 500 or attempt == 2:
                raise RuntimeError(f"HTTP {exc.code} for {path}") from exc
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise RuntimeError(f"no response for {path}")
        time.sleep(3 * (attempt + 1))


def junk_strings(obj, path="") -> list[str]:
    """Display strings like 'N/A', '#N/A', 'undefined' anywhere in a payload."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += junk_strings(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:200]):
            out += junk_strings(v, f"{path}[{i}]")
    elif isinstance(obj, str) and (JUNK.match(obj.strip()) or "#N/A" in obj or "undefined" in obj):
        out.append(f"{path} = {obj!r}")
    return out


def empty_slots(ped, generations: int = 5) -> int:
    missing = 0

    def walk(node, g):
        nonlocal missing
        if g > generations:
            return
        if not node:
            missing += 2 ** (generations - g + 1) - 1
            return
        walk(node.get("sire"), g + 1)
        walk(node.get("dam"), g + 1)

    walk((ped or {}).get("sire"), 1)
    walk((ped or {}).get("dam"), 1)
    return missing


def run_api(audit: Audit, api: str, sample: int) -> None:
    q = urllib.parse.quote
    stallions = get(api, "/api/stallions").get("stallions", [])
    top = stallions[:sample]
    junk, wrong_earn, earn_total, no_progeny, repeated_grade, wins_total, ambiguous = [], [], 0, [], [], 0, []
    broken = []
    for s in top:
        name = s["name"]
        try:
            d = get(api, f"/api/horses/{q(name)}")
        except RuntimeError as exc:
            broken.append(f"{name}: {exc}")
            continue
        if d.get("ambiguous"):
            ambiguous.append(name)
            continue
        junk += [f"{name}: {j}" for j in junk_strings({k: v for k, v in d.items() if k not in ("pedigree", "raw")})]
        progeny = d.get("top_progeny") or []
        if not progeny:
            no_progeny.append(name)
        for p in progeny[:10]:
            if not p.get("earnings"):
                continue
            earn_total += 1
            try:
                pd = get(api, f"/api/horses/{q(p['name'])}")
            except RuntimeError:
                continue  # an unscraped or ambiguous progeny name; not this check's concern
            seasons = sum(r.get("earnings") or 0 for r in (pd.get("race_record") or []))
            if seasons and abs(seasons - p["earnings"]) > max(100, 0.01 * seasons):
                wrong_earn.append(f"{p['name']} (by {name}): top progeny ${p['earnings']:,} vs race record ${seasons:,}")
        for w in d.get("race_wins") or d.get("wins") or []:
            wins_total += 1
            if GRADE_IN_NAME.search(w.get("race_name") or "") and (w.get("class") or w.get("grade")):
                repeated_grade.append(f"{name}: {w.get('race_name')} + {w.get('class') or w.get('grade')}")
    audit.check("directory stallions whose profile fails to load", len(broken), len(top), broken)
    audit.check("stallion profiles resolve to one horse", len(ambiguous), len(top), ambiguous)
    audit.check("junk labels (N/A, undefined) on stallion pages", len(junk), len(top), junk)
    audit.check("leading stallions with no top progeny", len(no_progeny), len(top), no_progeny, max_bad=2)
    audit.check("top progeny earnings match the race record", len(wrong_earn), earn_total, wrong_earn)
    audit.check("race names that repeat the grade", len(repeated_grade), wins_total, repeated_grade,
                note="e.g. 'IROQUOIS STAKES (GR. 3) G3'")

    catalogs = get(api, "/api/sales/upcoming").get("catalogs", [])
    gaps, no_cross, no_auction, no_market, hip_junk, hips_total = [], [], [], [], [], 0
    rng = random.Random(dt.date.today().toordinal())
    for cat in catalogs:
        lots = get(api, f"/api/sales/upcoming/{q(cat['id'])}/lots?limit=5000").get("lots", [])
        for lot in rng.sample(lots, min(sample, len(lots))):
            hip = lot.get("hip")
            label = f"{cat['id']} hip {hip}"
            hips_total += 1
            try:
                d = get(api, f"/api/sales/upcoming/{q(cat['id'])}/lots/{q(str(hip))}")
            except RuntimeError as exc:
                hip_junk.append(f"{label}: page failed ({exc})")
                continue
            n = empty_slots(d.get("pedigree"))
            if n:
                gaps.append(f"{label}: {n} of 62 ancestors missing")
            if not d.get("similar_crosses"):
                no_cross.append(label)
            if not d.get("auction_history"):
                no_auction.append(label)
            if not (d.get("market_prediction") or d.get("expected_market")):
                no_market.append(label)
            hip_junk += [f"{label}: {j}" for j in junk_strings(d.get("lot") or {})]
    audit.check("hip pedigrees with missing ancestors", len(gaps), hips_total, gaps, max_bad=hips_total // 10,
                note="some old female lines are genuinely unrecorded")
    audit.check("hips with no similar crosses", len(no_cross), hips_total, no_cross, max_bad=hips_total // 5)
    audit.check("hips with an empty auction history", len(no_auction), hips_total, no_auction, max_bad=hips_total // 3)
    audit.check("hips with no market projection", len(no_market), hips_total, no_market, max_bad=hips_total // 10)
    audit.check("junk labels on hip pages", len(hip_junk), hips_total, hip_junk)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default=API)
    ap.add_argument("--sample", type=int, default=20, help="stallions and hips per catalog to check")
    ap.add_argument("--skip-api", action="store_true")
    ap.add_argument("--skip-db", action="store_true")
    args = ap.parse_args()
    audit = Audit()
    started = time.time()
    if not args.skip_db:
        run_db(audit)
    if not args.skip_api:
        try:
            run_api(audit, args.api, args.sample)
        except Exception as exc:
            audit.check("live site reachable", 1, 1, [f"{exc.__class__.__name__}: {exc}"])
    today = dt.date.today().isoformat()
    lines = [f"# Data audit {today}", "", f"{len(audit.failed)} of {len(audit.results)} checks failed "
             f"({time.time() - started:.0f}s).", "", "| Check | Result | Bad / checked | Note |", "|---|---|---|---|"]
    for r in audit.results:
        lines.append(f"| {r['check']} | {'ok' if r['ok'] else '**FAIL**'} | {r['bad']} / {r['total']} | {r['note']} |")
    for r in audit.failed:
        lines += ["", f"## {r['check']}", *[f"- {e}" for e in r["examples"]]]
    out = ROOT / "logs" / "audit" / f"{today}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(f"report: {out}")
    if not args.skip_db:
        from crossr_core import railway_db

        try:
            with railway_db.connect() as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS data_audit_runs (
                    run_at TIMESTAMPTZ NOT NULL DEFAULT now(), failed INTEGER NOT NULL,
                    total INTEGER NOT NULL, results JSONB NOT NULL)""")
                conn.execute("INSERT INTO data_audit_runs (failed, total, results) VALUES (%s, %s, %s)",
                             (len(audit.failed), len(audit.results), json.dumps(audit.results)))
        except Exception as exc:
            print(f"could not record the run: {exc}")
    sys.exit(1 if audit.failed else 0)


if __name__ == "__main__":
    main()

"""Dams whose sale lots have no broodmare sire: find each on Equibase, then fill.

The list (state/shared/missing-damsire-dams.csv, from
scripts/backfill_damsire_by_age.py's leftovers) holds one row per dam name
with the years of her lots. For each dam, one Equibase search lists every
namesake with foal year, sex and sire. Only thoroughbred fillies/mares foaled
in the dam's age window are kept:

    last_sale_year - 27 <= foal year <= earliest_foal_year - 3

The search results are staged (dam_candidates_stage) and the next push fills
each lot on its own: among the kept namesakes, those old enough for that lot
(foaled 3-26 years before the lot's foal, or 3-27 before the sale when the
foal year is unknown) with the same country suffix. One distinct sire fills
the lot's damsire / damsire_key; existing values are never overwritten, and
every fill is logged in sales_lots_fill_log as source SOURCE.

When one namesake remains, her profile (race record, sire, foal year, sex) is
fetched into race_horses like any other horse.
"""

from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path

from equibase_scraper.queue import clean_name

JOB = "damsire-dams"
SOURCE = "damsire-scraped-dam"
LIST_PATH = Path(os.environ.get("CROSSR_DAMSIRE_DAMS")
                 or Path(__file__).resolve().parents[1] / "state" / "shared" / "missing-damsire-dams.csv")
MIN_AGE, MAX_AGE_AT_FOAL, MAX_AGE_AT_SALE = 3, 26, 27
DONE = {"found", "ambiguous", "not_found"}
DAM_SEXES = {"mare", "filly", "m", "f"}  # search lists spell it out, profiles abbreviate
_SUFFIX = re.compile(r"\(([A-Za-z]{2,4})\)")


def _int(value) -> int | None:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else None


def suffix(name: str) -> str:
    """Country suffix of a horse name, "" for none: "Wonder Woman (GB)" -> "GB"."""
    found = _SUFFIX.search(name or "")
    return found.group(1).upper() if found else ""


def load_list(path: Path = LIST_PATH) -> list[dict]:
    """The dams, most lots since 2010 first. Missing file: nothing to do."""
    if not path.exists():
        return []
    items = []
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("dam") or "").strip()
            name_key = clean_name(name)
            last, earliest = _int(row.get("last_sale_year")), _int(row.get("earliest_foal_year"))
            if not name_key:
                continue
            window = None
            if last and earliest:
                window = (last - MAX_AGE_AT_SALE, earliest - MIN_AGE)
            elif last:
                window = (last - MAX_AGE_AT_SALE, last - MIN_AGE)
            items.append({
                "name": name, "name_key": name_key, "key": f"dam:{name_key}", "yob_range": window,
                "lots": _int(row.get("lots")) or 0, "recent": _int(row.get("lots_2010_plus")) or 0,
                "reason": row.get("reason") or "",
            })
    items.sort(key=lambda it: (-it["recent"], -it["lots"], it["name_key"]))
    return items


def build_queue(items: list[dict], states: dict, limit: int | None = None) -> list[dict]:
    todo = [it for it in items if (states.get(it["key"]) or {}).get("status") not in DONE]
    return todo[:limit] if limit else todo


def keep(candidates: list[dict], window: tuple[int, int] | None) -> list[dict]:
    """Thoroughbred fillies/mares foaled inside the window."""
    out = []
    for row in candidates:
        yob = _int(row.get("yob"))
        if (row.get("breed") or "TB").upper() != "TB" or (row.get("sex") or "").lower() not in DAM_SEXES:
            continue
        if yob is None or (window and not window[0] <= yob <= window[1]):
            continue
        if not (row.get("sire") or "").strip():
            continue
        # Equibase marks foreign-bred horses with a leading "=" ("=Medicean (GB)").
        out.append({"name": row.get("name") or "", "yob": yob, "sire": row["sire"].strip().lstrip("=").strip(),
                    "refno": row.get("refno") or "", "registry": row.get("registry") or "",
                    "url": row.get("url") or ""})
    return out


def status_of(kept: list[dict]) -> str:
    if not kept:
        return "not_found"
    return "found" if len({clean_name(c["sire"]) for c in kept}) == 1 else "ambiguous"


def stage(local, item: dict, kept: list[dict]) -> None:
    local.execute(
        "INSERT OR REPLACE INTO dam_candidates_stage (name_key, name, candidates) VALUES (?, ?, ?)",
        (item["name_key"], item["name"], json.dumps(kept)),
    )


# ---------------------------------------------------------------------------
# push: fill the lots (inside stage.push's transaction)
# ---------------------------------------------------------------------------

def _N(x: str) -> str:
    """Dam name as in scripts/backfill_damsire_by_age.py: no (...), letters/digits/spaces, upper."""
    return f"upper(regexp_replace(regexp_replace(coalesce({x},''), '\\(.*?\\)', '', 'g'), '[^A-Za-z0-9 ]', '', 'g'))"


def _sfx(x: str) -> str:
    return f"upper(coalesce(substring({x} from '\\(([A-Za-z]{{2,4}})\\)'), ''))"


def push_fills(pg, rows: list[dict]) -> int:
    """Fill blank damsires from the staged candidates. Returns lots filled."""
    cands = [(c, r["name"]) for r in rows for c in json.loads(r["candidates"] or "[]")]
    if not cands:
        return 0
    pg.execute("DROP TABLE IF EXISTS _dam_cand")
    pg.execute("CREATE TEMP TABLE _dam_cand (name TEXT, yob INT, sire TEXT) ON COMMIT DROP")
    with pg.cursor() as cur:
        with cur.copy("COPY _dam_cand (name, yob, sire) FROM STDIN") as copy:
            for c, list_name in cands:
                copy.write_row([c["name"] or list_name, c["yob"], c["sire"]])
    pg.execute(f"CREATE TEMP TABLE _dam_cand_k ON COMMIT DROP AS SELECT {_N('name')} AS k, {_sfx('name')} AS sfx, "
               f"yob, sire, trim(regexp_replace(lower(regexp_replace(sire, '\\(.*?\\)', '', 'g')), '\\s+', ' ', 'g')) "
               "AS sire_key FROM _dam_cand")
    pg.execute("CREATE INDEX ON _dam_cand_k (k)")
    # One row per blank lot with exactly one sire among the namesakes that fit it.
    pg.execute(
        f"""CREATE TEMP TABLE _dam_fill ON COMMIT DROP AS
            SELECT s._rid, s.source_file, s.hip, s.name_key, min(c.sire) AS damsire, min(c.sire_key) AS damsire_key
            FROM sales_lots s JOIN _dam_cand_k c ON c.k = {_N('s.dam')}
             AND (c.sfx = {_sfx('s.dam')} OR ({_sfx('s.dam')} = '' AND c.sfx = 'CAN'))
             AND CASE WHEN s.birth_year ~ '^[0-9]{{4}}$'
                      THEN c.yob BETWEEN s.birth_year::int - {MAX_AGE_AT_FOAL} AND s.birth_year::int - {MIN_AGE}
                      ELSE s.catalog_year ~ '^[0-9]{{4}}$'
                           AND c.yob BETWEEN s.catalog_year::int - {MAX_AGE_AT_SALE} AND s.catalog_year::int - {MIN_AGE}
                 END
            WHERE coalesce(s.damsire, '') = '' AND {_N('s.dam')} IN (SELECT k FROM _dam_cand_k)
            GROUP BY s._rid, s.source_file, s.hip, s.name_key
            HAVING count(DISTINCT c.sire_key) = 1"""
    )
    pg.execute(
        """CREATE TABLE IF NOT EXISTS sales_lots_fill_log (
               source_file TEXT, hip TEXT, name_key TEXT, field TEXT, value TEXT,
               source TEXT, filled_at TIMESTAMPTZ NOT NULL DEFAULT now())"""
    )
    filled = pg.execute(
        """UPDATE sales_lots s SET damsire = f.damsire, damsire_key = f.damsire_key
           FROM _dam_fill f
           WHERE s._rid = f._rid AND coalesce(s.damsire, '') = ''"""
    ).rowcount
    pg.execute(
        "INSERT INTO sales_lots_fill_log (source_file, hip, name_key, field, value, source) "
        "SELECT source_file, hip, name_key, 'damsire', damsire, %s FROM _dam_fill", (SOURCE,)
    )
    return filled

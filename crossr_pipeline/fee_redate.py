"""Rebuild stud_fees from the stallion-ranking CSVs, by breeding season.

Each ranking file's "<year> Stud Fee / Farm" header says which season its fees
are for (stallion_rankings.stud_fee_season): next season for 2008–2022 and
2024–25 lists, the same season for 2007/2023/2026, and 2–4 seasons back for
2001–2005 ("1998 Stud Fee" on the 2001 lists). The 2006 files state no year;
they are dated file by file against Racing Post (UNDATED_FILES), and a file
with no clear match is left out.

Racing Post, though, matches the 2001–2005 fees to the list year too (≈80%),
not the header's season (≈20%). ``early`` picks which to trust for lists up
to 2007: "header" (default, the files as written) or "list-year".

Per stallion and season, in priority order:
  1. user        values the user gave (Source List 'user')
  2. CSV         ranking fees keyed by season; several lists agreeing merge
                 their Source Lists, disagreeing ones keep the most common fee
  3. Racing Post only where the CSVs have no fee for that season
  4. Web lookup  only where neither has one
  -  N/A rows    a ranking row with no fee keeps the stallion on that list
                 year (farm, roster) unless a fee lands there
CSV and Racing Post disagreeing on a season is counted as a conflict; the CSV
value is kept.

    python -m crossr_pipeline fees-redate [--early list-year]            # dry run
    python -m crossr_pipeline fees-redate [--early list-year] --apply    # back up, replace
"""

from __future__ import annotations

import re
import time
from collections import Counter, defaultdict

from crossr_pipeline.racing_post import format_fee, is_usa
from equibase_scraper.queue import clean_name

COLUMNS = ("Year", "Stallion", "Stud Fee", "Farm", "Source List", "Notes")
NO_FEE = {"", "N/A", "$0", "0", "NONE"}
EXAMPLES = ("NOT THIS TIME", "INTO MISCHIEF", "CURLIN", "FLIGHTLINE")
EARLY_LAST = 2007
LIST_NAMES = {
    "General": "Leading Sire Rankings",
    "First-Crop": "Leading First Crop Sires",
    "Second-Crop": "Leading Second-Crop Sires",
    "Third-Crop": "Leading Third-Crop Sires",
    "Two-Year-Old": "Leading Two-Year-Old Sires",
    "Lifetime AEI": "Leading Sires by AEI",
}
DATED = "Ranking CSV fee"


def norm_fee(text) -> str:
    return re.sub(r"\s+", " ", str(text or "").split("\n")[0]).strip().upper()


def fee_number(text) -> int | None:
    match = re.search(r"\$\s*([\d,]+)", str(text or ""))
    return int(match.group(1).replace(",", "")) if match else None


# Files whose fee header has no year ("Stud Fee / Farm"), dated by matching
# their fees against Racing Post at each offset (2026-10-27). None = no clear
# winner: those fees stay out rather than be guessed.
UNDATED_FILES = {
    "2006/2006StallionRankings - Leading Sire Rankings.csv": 0,          # 89/101 at +0, next 42/95
    "2006/2006StallionRankings - Leading Second-Crop Sires.csv": 0,      # 26/29, next 12/29
    "2006/2006StallionRankings - Leading Third-Crop Sires.csv": 0,       # 27/33, next 13/32
    "2006/2006StallionRankings - Leading Two-Year-Old Sires.csv": 0,     # 95/105, next 50/104
    "2006/2006StallionRankings - Leading First Crop Sires.csv": None,    # 26/29 vs 22/28 at -1
}


def season_for(year: int, stated, early: str = "header", source_file: str | None = None) -> int | None:
    """The breeding season a ranking row's fee is for, from its file header."""
    if early == "list-year" and year <= EARLY_LAST:
        return year
    if str(stated or "").isdigit():
        return int(stated)
    offset = UNDATED_FILES.get(source_file or "")
    return None if offset is None else year + offset


def rebuild(ranking_rows: list[dict], fee_rows: list[dict], rp: dict, early: str = "header"):
    """ranking_rows: stallion_rankings; fee_rows: current stud_fees (for user and
    web values); rp: key -> racing_post_fees rows. Returns (rows, stats, conflicts)."""
    stats: Counter = Counter()
    names: dict[str, Counter] = defaultdict(Counter)
    csv_fees: dict[tuple, list[dict]] = defaultdict(list)
    placeholders: dict[tuple, dict] = {}
    for r in ranking_rows:
        if not str(r.get("year") or "").isdigit() or r.get("list") not in LIST_NAMES:
            continue
        key = clean_name(r["stallion"] or "")
        if not key:
            continue
        names[key][r["stallion"]] += 1
        year = int(r["year"])
        raw_lines = str(r.get("stud_fee_raw") or "").split("\n")
        farm = r.get("farm") or (raw_lines[1].strip() if len(raw_lines) > 1 else "")
        source = LIST_NAMES[r["list"]]
        fee = (r.get("stud_fee") or "").strip()
        if norm_fee(fee) in NO_FEE:
            placeholders.setdefault((key, year), {
                "Year": str(year), "Stallion": r["stallion"], "Stud Fee": "N/A", "Farm": farm,
                "Source List": source, "Notes": None,
            })
            continue
        season = season_for(year, r.get("stud_fee_season"), early, r.get("source_file"))
        if season is None:
            stats["CSV fees dropped: file header has no season"] += 1
            continue
        stats["CSV fee rows"] += 1
        csv_fees[(key, season)].append({
            "Year": str(season), "Stallion": r["stallion"], "Stud Fee": fee, "Farm": farm,
            "Source List": source, "Notes": f"{DATED}, list year {year}", "_year": year,
        })

    user, web = {}, {}
    for r in fee_rows:
        if not str(r.get("Year") or "").isdigit():
            continue
        slot = (clean_name(r["Stallion"] or ""), int(r["Year"]))
        if r.get("Source List") == "user":
            user[slot] = r
        elif r.get("Source List") == "Web lookup":
            web[slot] = r

    rp_best: dict[tuple, dict] = {}
    for key, rows in rp.items():
        by_year = defaultdict(list)
        for r in rows:
            by_year[r["year"]].append(r)
        for year, options in by_year.items():
            options.sort(key=lambda r: (not is_usa(r), r["is_private"], r["stud_fee"] is None))
            best = options[0]
            if best["stud_fee"] is None and not best["is_private"]:
                continue
            notes = "; ".join(x for x in (f"Racing Post {best['rp_horse_id']}", best["country"], best["currency"]) if x)
            rp_best[(key, year)] = {
                "Year": str(year), "Stallion": best["stallion"], "Stud Fee": format_fee(best),
                "Farm": best["standing"] or "", "Source List": "Racing Post fee history", "Notes": notes,
            }

    out: dict[tuple, dict] = {}
    conflicts = []
    for slot, cands in csv_fees.items():
        fees = Counter(norm_fee(c["Stud Fee"]) for c in cands)
        top = fees.most_common(1)[0][0]
        chosen = dict(next(c for c in sorted(cands, key=lambda c: -c["_year"]) if norm_fee(c["Stud Fee"]) == top))
        chosen["Source List"] = "; ".join(sorted({c["Source List"] for c in cands if norm_fee(c["Stud Fee"]) == top}))
        chosen.pop("_year")
        if len(fees) > 1:
            stats["seasons where CSV lists disagree"] += 1
        stats["CSV rows merged into one season"] += len(cands) - 1
        out[slot] = chosen
        rp_row = rp_best.get(slot)
        if rp_row and fee_number(rp_row["Stud Fee"]) is not None and fee_number(chosen["Stud Fee"]) is not None \
                and fee_number(rp_row["Stud Fee"]) != fee_number(chosen["Stud Fee"]):
            conflicts.append((slot[0], slot[1], chosen["Stud Fee"], rp_row["Stud Fee"]))
    stats["seasons from CSV"] = len(out)
    for slot, row in rp_best.items():
        if slot not in out:
            out[slot] = row
            stats["seasons filled from Racing Post"] += 1
    for slot, row in web.items():
        if slot not in out:
            out[slot] = dict(row)
            stats["seasons from web lookup"] += 1
        else:
            stats["web lookups superseded"] += 1
    for slot, row in user.items():
        if slot in out:
            stats["user values overriding another source"] += 1
        out[slot] = dict(row)
        stats["seasons from user"] += 1
    for slot, row in placeholders.items():
        if slot not in out:
            out[slot] = row
            stats["N/A rows kept"] += 1
    stats["CSV vs Racing Post conflicts (CSV kept)"] = len(conflicts)

    rows = []
    for (key, _season), row in out.items():
        if names.get(key):
            row["Stallion"] = names[key].most_common(1)[0][0]
        rows.append({c: row.get(c) for c in COLUMNS})
    rows.sort(key=lambda r: (clean_name(r["Stallion"]), int(r["Year"])))
    return rows, stats, conflicts


def load(conn) -> tuple[list[dict], list[dict], dict]:
    ranking_rows = [dict(r) for r in conn.execute(
        "SELECT stallion, year, list, stud_fee, stud_fee_season, stud_fee_raw, farm, source_file FROM stallion_rankings")]
    cols = ", ".join(f'"{c}"' for c in COLUMNS)
    fee_rows = [dict(r) for r in conn.execute(f"SELECT {cols} FROM stud_fees")]
    rp: dict = defaultdict(list)
    for r in conn.execute("SELECT stallion_key, stallion, rp_horse_id, year, stud_fee, currency, is_private, "
                          "country, standing FROM racing_post_fees"):
        rp[r["stallion_key"]].append(dict(r))
    return ranking_rows, fee_rows, rp


def fee_table(rows: list[dict], key: str, years=range(2015, 2028)) -> list[str]:
    by = {int(r["Year"]): r for r in rows if clean_name(r["Stallion"]) == key and str(r["Year"]).isdigit()}
    return [f"{y}: {by[y]['Stud Fee']:<10} {(by[y]['Source List'] or '')[:34]}" for y in years if y in by]


def gaps(rows: list[dict]) -> int:
    have = defaultdict(set)
    for r in rows:
        if norm_fee(r["Stud Fee"]) not in NO_FEE and str(r["Year"]).isdigit():
            have[clean_name(r["Stallion"])].add(int(r["Year"]))
    return sum(len(set(range(min(y), max(y) + 1)) - y) for y in have.values() if y)


def apply(conn, new_rows: list[dict]) -> str:
    backup = f"stud_fees_backup_{time.strftime('%Y%m%d_%H%M%S')}"
    cols = ", ".join(f'"{c}"' for c in COLUMNS)
    with conn.transaction():
        conn.execute(f'CREATE TABLE "{backup}" AS SELECT * FROM stud_fees')
        conn.execute("DELETE FROM stud_fees")
        with conn.cursor() as cur:
            with cur.copy(f"COPY stud_fees ({cols}) FROM STDIN") as copy:
                for r in new_rows:
                    copy.write_row([None if r.get(c) in ("", None) else str(r[c]) for c in COLUMNS])
    from equibase_scraper import pgdb

    pgdb.flush_versions(conn, ("stud_fees",))
    return backup

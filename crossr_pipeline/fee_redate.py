"""Re-date stud_fees by breeding season.

Ranking-list fees were stored under the ranking year, but most lists quote the
fee for a different season (stallion_rankings.stud_fee_season): usually the
next one, and the crop-sire lists the season the crop was conceived. This
rebuilds stud_fees with one fee per stallion and season, by priority:

  1. user        values the user gave (Source List 'user')
  2. Racing Post the stallion's fee history (racing_post_fees), US row first
  3. Web lookup  farm announcements found for gaps (URL in Notes)
  4. ranking     a ranking fee keyed by its stud_fee_season. Several for one
                 season: the same fee merges their Source Lists; different fees
                 keep the current-fee list (season = ranking year + 1), then
                 the most common fee
  -  N/A / $0    rows with no fee stay at their year (they carry the farm and
                 the roster year) unless a fee lands on that year
Ranking fees whose season cannot be found (no matching ranking row, or rows
that disagree) are dropped rather than guessed.

    python -m crossr_pipeline fees-redate            # dry run: counts + examples
    python -m crossr_pipeline fees-redate --apply    # back up, then replace stud_fees
"""

from __future__ import annotations

import re
import time
from collections import Counter, defaultdict

from crossr_pipeline.racing_post import format_fee, is_usa
from equibase_scraper.queue import clean_name

COLUMNS = ("Year", "Stallion", "Stud Fee", "Farm", "Source List", "Notes")
NO_FEE = {"", "N/A", "$0", "0"}
EXAMPLES = ("NOT THIS TIME", "INTO MISCHIEF", "CURLIN", "FLIGHTLINE")


def norm_fee(text) -> str:
    return re.sub(r"\s+", " ", str(text or "").split("\n")[0]).strip().upper()


def fee_number(text) -> int | None:
    match = re.search(r"([\d,]{3,})", norm_fee(text))
    return int(match.group(1).replace(",", "")) if match else None


DATED = "Ranking fee, season-dated"


def kind(row: dict) -> str:
    source = row.get("Source List") or ""
    if (row.get("Notes") or "").startswith(DATED):
        return "dated"
    if source == "user":
        return "user"
    if source.startswith("Racing Post"):
        return "rp"
    if source == "Web lookup":
        return "web"
    return "ranking"


def season_of(row: dict, rankings: dict) -> tuple[int | None, int | None]:
    """(season, offset) for a ranking-derived fee row, or (None, None)."""
    year = int(row["Year"])
    cands = rankings.get((clean_name(row["Stallion"]), year), [])
    fee = norm_fee(row["Stud Fee"])
    seasons = {s for f, s in cands if f == fee and s}
    if not seasons:
        number = fee_number(row["Stud Fee"])
        if number is not None:
            seasons = {s for f, s in cands if s and fee_number(f) == number}
    if len(seasons) != 1:
        return None, None
    season = seasons.pop()
    return season, season - year


def rebuild(rows: list[dict], rankings: dict, rp: dict) -> tuple[list[dict], Counter]:
    """rows: current stud_fees; rankings: (key, year) -> [(fee, season)];
    rp: key -> [racing_post_fees rows]. Returns (new rows, counts)."""
    stats: Counter = Counter()
    names: dict[str, Counter] = defaultdict(Counter)
    slots: dict[tuple[str, int], dict[str, list]] = defaultdict(lambda: defaultdict(list))
    placeholders: dict[tuple[str, int], dict] = {}
    for row in rows:
        if not str(row.get("Year") or "").isdigit():
            stats["dropped: no year"] += 1
            continue
        key = clean_name(row["Stallion"] or "")
        names[key][row["Stallion"]] += 1
        k = kind(row)
        year = int(row["Year"])
        if k == "ranking" and norm_fee(row["Stud Fee"]) in NO_FEE:
            placeholders.setdefault((key, year), row)
            continue
        if k == "ranking":
            season, offset = season_of(row, rankings)
            if season is None:
                stats["dropped: ranking fee with no season"] += 1
                continue
            stats["ranking fee kept in place" if offset == 0 else "ranking fee moved to its season"] += 1
            note = f"{DATED} (list year {year})"
            slots[(key, season)]["ranking"].append((offset, dict(row, Year=str(season), Notes=note)))
        elif k == "dated":  # re-dated on an earlier run: already on its season
            slots[(key, year)]["ranking"].append((1, row))
        else:  # user / web / Racing Post rows already sit on their season
            slots[(key, year)][k].append((0, row))
    for key, fee_rows in rp.items():
        by_year = defaultdict(list)
        for r in fee_rows:
            by_year[r["year"]].append(r)
        for year, options in by_year.items():
            options.sort(key=lambda r: (not is_usa(r), r["is_private"], r["stud_fee"] is None))
            best = options[0]
            if best["stud_fee"] is None and not best["is_private"]:
                continue
            notes = "; ".join(x for x in (f"Racing Post {best['rp_horse_id']}", best["country"], best["currency"]) if x)
            slots[(key, year)]["rp"].append((0, {
                "Year": str(year), "Stallion": best["stallion"], "Stud Fee": format_fee(best),
                "Farm": best["standing"] or "", "Source List": "Racing Post fee history", "Notes": notes,
            }))

    out = []
    for (key, season), cands in slots.items():
        display = names[key].most_common(1)[0][0] if names.get(key) else None
        chosen = None
        for k in ("user", "rp", "web"):
            if cands.get(k):
                chosen = dict(cands[k][0][1])
                stats[f"season from {k}"] += 1
                if cands.get("ranking"):
                    stats[f"ranking fee overruled by {k}"] += len(cands["ranking"])
                break
        if chosen is None:
            ranking = cands["ranking"]
            fees = Counter(norm_fee(r["Stud Fee"]) for _, r in ranking)
            if len(fees) == 1:
                chosen = dict(ranking[0][1])
                sources = sorted({s for _, r in ranking for s in (r["Source List"] or "").split("; ") if s})
                chosen["Source List"] = "; ".join(sources)
                stats["season from ranking"] += 1
                stats["ranking rows merged"] += len(ranking) - 1
            else:
                ranking.sort(key=lambda t: (t[0] != 1, -fees[norm_fee(t[1]["Stud Fee"])]))
                chosen = dict(ranking[0][1])
                stats["season from ranking (fees disagreed)"] += 1
                stats["ranking rows merged"] += len(ranking) - 1
        if display:
            chosen["Stallion"] = display
        out.append(chosen)
        placeholders.pop((key, season), None)
    for row in placeholders.values():
        out.append(row)
        stats["N/A rows kept"] += 1
    out.sort(key=lambda r: (clean_name(r["Stallion"]), int(r["Year"])))
    return [{c: r.get(c) for c in COLUMNS} for r in out], stats


def load(conn) -> tuple[list[dict], dict, dict]:
    cols = ", ".join(f'"{c}"' for c in COLUMNS)
    rows = [dict(r) for r in conn.execute(f"SELECT {cols} FROM stud_fees")]
    rankings: dict = defaultdict(list)
    for r in conn.execute("SELECT stallion, year, stud_fee, stud_fee_season FROM stallion_rankings"):
        season = int(r["stud_fee_season"]) if str(r["stud_fee_season"] or "").isdigit() else None
        if str(r["year"] or "").isdigit():
            rankings[(clean_name(r["stallion"] or ""), int(r["year"]))].append((norm_fee(r["stud_fee"]), season))
    rp: dict = defaultdict(list)
    for r in conn.execute("SELECT stallion_key, stallion, rp_horse_id, year, stud_fee, currency, is_private, "
                          "country, standing FROM racing_post_fees"):
        rp[r["stallion_key"]].append(dict(r))
    return rows, rankings, rp


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

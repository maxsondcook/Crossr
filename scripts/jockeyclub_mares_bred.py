"""Load The Jockey Club's Report of Mares Bred into breeding_seasons.

The report (jockeyclub.com -> Resources -> Report of Mares Bred) lists every
stallion that covered mares in North America in the current breeding season,
with mares bred and state. It fills in through the year as farms report (the
final 2025 report had 1,017 stallions), so run this weekly. It is one page,
so one request per run; jockeyclub.com's robots.txt allows crawling (with a
120 s crawl delay, far above our once-a-week rate).

BloodHorse's Stallion Register is behind Incapsula bot protection, so it is
not scraped; this public report is the complete official list instead.

Usage:
    python3 scripts/jockeyclub_mares_bred.py            # dry run: show what would change
    python3 scripts/jockeyclub_mares_bred.py --apply    # write to DATABASE_URL

Rows are upserted per (breeding_year, stallion): mares bred and state are
updated, live-foal columns from the later foaling report are left alone.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crossr_core import railway_db, sample_db  # noqa: E402

URL = "https://www.jockeyclub.com/default.asp?section=Resources&area=16"
SOURCE = "The Jockey Club Report of Mares Bred"


def fetch(url: str = URL) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Crossr/1.0 (weekly mares-bred update)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", "replace")


def parse(page: str) -> tuple[int, list[dict]]:
    m = re.search(r"Mares Reported Bred to Thoroughbred Stallions in (\d{4})", page)
    if not m:
        raise SystemExit("Could not find the report year on the page; the layout may have changed.")
    year = int(m.group(1))
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S | re.I):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)]
        if len(cells) >= 3 and cells[1].replace(",", "").isdigit() and cells[0]:
            rows.append({"stallion": cells[0], "mares_bred": cells[1].replace(",", ""), "state": cells[2]})
    if len(rows) < 100:
        raise SystemExit(f"Only {len(rows)} stallions parsed; refusing to load a partial page.")
    return year, rows


def apply(year: int, rows: list[dict], write: bool) -> dict:
    with railway_db.connect() as conn:
        existing = {
            sample_db.name_key(name): (name, mares, state)
            for name, mares, state in conn.execute(
                "SELECT stallion, mares_bred, state FROM breeding_seasons WHERE breeding_year = %s", (str(year),)
            )
        }
        inserts, updates = [], []
        for r in rows:
            key = sample_db.name_key(r["stallion"])
            old = existing.get(key)
            if old is None:
                inserts.append(r)
            elif (str(old[1] or ""), str(old[2] or "")) != (r["mares_bred"], r["state"]):
                updates.append((r, old[0]))
        if write and (inserts or updates):
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO breeding_seasons (breeding_year, stallion, mares_bred, state, source) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    [(str(year), r["stallion"], r["mares_bred"], r["state"], SOURCE) for r in inserts],
                )
                cur.executemany(
                    "UPDATE breeding_seasons SET mares_bred = %s, state = %s, source = %s "
                    "WHERE breeding_year = %s AND stallion = %s",
                    [(r["mares_bred"], r["state"], SOURCE, str(year), stored) for r, stored in updates],
                )
            total = conn.execute("SELECT count(*) FROM breeding_seasons").fetchone()[0]
            railway_db._bump(conn, "breeding_seasons", int(total))
    return {"year": year, "on_page": len(rows), "already_stored": len(existing),
            "new": [r["stallion"] for r in inserts], "updated": len(updates)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write to the database (default: dry run)")
    ap.add_argument("--file", help="parse a saved copy of the page instead of fetching it")
    args = ap.parse_args()
    page = Path(args.file).read_text() if args.file else fetch()
    year, rows = parse(page)
    result = apply(year, rows, write=args.apply)
    print(f"{result['year']} report: {result['on_page']} stallions on the page, "
          f"{result['already_stored']} already stored; {len(result['new'])} new, {result['updated']} updated"
          f"{'' if args.apply else ' (dry run, nothing written)'}")
    if result["new"]:
        print("new:", ", ".join(result["new"][:60]) + (" ..." if len(result["new"]) > 60 else ""))


if __name__ == "__main__":
    main()

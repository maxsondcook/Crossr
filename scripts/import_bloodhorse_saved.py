"""Load BloodHorse sire-list pages saved from a browser into stallion_rankings.

BloodHorse is behind bot protection, so nothing here fetches it. Save each
list page from your own browser (File > Save Page As..., "Webpage, HTML
Only") into stallion_rankings_data/saved/<year>/; how-to in
docs/stallion-rankings.md. Each page is parsed with the archive scraper's
parser (bloodhorse_sirelists/scrape_sirelists.py), written as the usual CSV
(stallion_rankings_data/<year>/<year>StallionRankings - <list>.csv) and
loaded with the same CSV loader, so rows have the same shape as earlier years.

Which list and year a file is: from the "saved from url" line Chrome and
Safari put in the file (seoName=...&year=...), else from the file name
("2026_general.html", "general.html" with --year).

    python3 scripts/import_bloodhorse_saved.py                 # dry run: what would load
    python3 scripts/import_bloodhorse_saved.py --apply         # write CSVs, back up, load
    python3 scripts/import_bloodhorse_saved.py --year 2026 --folder ~/Downloads/sirelists

--apply backs up the stallion_rankings rows of the lists it replaces to
db-backups/, replaces only those lists (by source file), and bumps the
table version so the API reloads.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import re
import sys
import time
import types
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RANKINGS = ROOT / "stallion_rankings_data"
SAVED = RANKINGS / "saved"
BACKUPS = ROOT / "db-backups"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


def identify(path: Path, html: str, default_year: int | None, pages: dict) -> tuple[str | None, int | None]:
    """(seoName, year) of a saved page."""
    seo, year = None, None
    saved = re.search(r"saved from url=\(\d+\)(\S+)", html[:4000])
    for url in ([saved.group(1)] if saved else []) + re.findall(r"https?://[^\s\"'<>]*seoName=[^\s\"'<>]+", html)[:3]:
        query = parse_qs(urlparse(url.replace("&amp;", "&")).query)
        seo = seo or (query.get("seoName") or [None])[0]
        y = (query.get("year") or [""])[0]
        year = year or (int(y) if y.isdigit() else None)
    stem = path.stem.lower().replace(" ", "-").replace("_", "-")
    if not year:
        found = re.search(r"(20\d\d)", stem)
        year = int(found.group(1)) if found else default_year
    if not seo:
        # longest match wins: "international-first-crop" before "first-crop"
        for name in sorted(pages, key=len, reverse=True):
            if name in stem:
                seo = name
                break
    return seo, year


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--folder", type=Path, help="Folder of saved pages (default stallion_rankings_data/saved/<year> "
                                                "or stallion_rankings_data/saved)")
    ap.add_argument("--year", type=int, help="Year for files whose page and name do not say")
    ap.add_argument("--apply", action="store_true", help="Write the CSVs and load them (default: dry run)")
    args = ap.parse_args()

    try:  # the archive scraper imports requests for fetching; parsing does not need it
        import requests  # noqa: F401
    except ImportError:
        sys.modules["requests"] = types.ModuleType("requests")
    scraper = _load("scrape_sirelists", RANKINGS / "bloodhorse_sirelists" / "scrape_sirelists.py")
    builder = _load("build_stallion_rankings_database", RANKINGS / "build_stallion_rankings_database.py")
    pages = {p.seo_name: p for p in scraper.PAGES}

    folder = args.folder or (SAVED / str(args.year) if args.year and (SAVED / str(args.year)).is_dir() else SAVED)
    files = sorted(p for p in folder.expanduser().rglob("*") if p.suffix.lower() in (".html", ".htm"))
    if not files:
        print(f"No .html files in {folder}. See docs/stallion-rankings.md.")
        return 1

    outputs: list[tuple[Path, int, list[list[str]]]] = []
    problems = 0
    for path in files:
        html = path.read_text(encoding="utf-8", errors="ignore")
        seo, year = identify(path, html, args.year, pages)
        if scraper.is_blocked(html) or scraper.is_login_wall(html):
            print(f"  SKIP {path.name}: saved page is a bot check or sign-in wall, not the list")
            problems += 1
            continue
        if seo not in pages or not year:
            print(f"  SKIP {path.name}: can't tell which list/year (seoName={seo}, year={year}); "
                  f"rename it like 2026_general.html")
            problems += 1
            continue
        page = pages[seo]
        tables = scraper.parse_page(html, page, year)
        for key, title in page.outputs.items():
            rows = tables.get(key) or []
            data = [r for r in rows if r and str(r[0]).strip().isdigit()]
            if not data:
                print(f"  SKIP {path.name}: no '{title}' table with ranked rows")
                problems += 1
                continue
            out = RANKINGS / str(year) / f"{year}StallionRankings - {title}.csv"
            outputs.append((out, year, rows))
            print(f"  {path.name} -> {year} {title}: {len(data)} stallions (top: {data[0][1].splitlines()[0]!r})")

    if not outputs:
        return 1
    if not args.apply:
        print(f"dry run: {len(outputs)} list(s) would load, {problems} problem(s); nothing written (use --apply)")
        return 0

    from crossr_core import railway_db, sample_db

    records = []
    for out, year, rows in outputs:
        scraper.write_csv(out, rows)
        records.extend(builder.load_file(out, str(year)))
    files_loaded = sorted({r["source_file"] for r in records if r.get("source_file")})
    BACKUPS.mkdir(exist_ok=True)
    backup = BACKUPS / f"stallion_rankings_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    columns = sample_db.TABLES["stallion_rankings"]
    with railway_db.connect() as conn, backup.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        col_sql = ", ".join(f'"{c}"' for c in columns)
        for row in conn.execute(f"SELECT {col_sql} FROM stallion_rankings WHERE source_file = ANY(%s)", (files_loaded,)):
            writer.writerow(row)
    result = sample_db.replace_by_file("stallion_rankings", records)
    print(f"backed up the replaced lists to {backup.relative_to(ROOT)}; loaded {len(records)} rows "
          f"from {len(files_loaded)} list(s): {result}")
    return 0 if not problems else 2


if __name__ == "__main__":
    raise SystemExit(main())

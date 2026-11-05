"""Watch racing news for stallions being pensioned or dying; queue each match for review.

Reads Thoroughbred Daily News' RSS feed (one request; its robots.txt allows
general crawlers with a 10 s crawl delay, far above a daily run). A story whose
headline names a stallion in the registry together with a status word
("pensioned", "retired from stud", "dies", "euthanized", ...) becomes a
suggestion in stallion_status_suggestions with the headline and link. Nothing
changes on the site until a suggestion is approved:

    python3 scripts/stallion_status.py suggestions          # review
    python3 scripts/stallion_status.py approve "War Front"   # -> stallion_status_overrides
    python3 scripts/stallion_status.py reject "Frosted Over"

Usage:
    python3 scripts/stallion_news_watch.py             # dry run: print matches
    python3 scripts/stallion_news_watch.py --apply     # store new suggestions
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crossr_core import stallion_status as ss  # noqa: E402

FEEDS = ["https://www.thoroughbreddailynews.com/feed/"]
DEATH = re.compile(r"\b(dies|died|death of|euthani[sz]ed|put down|passes away|passed away|succumbs|lost to)\b", re.I)
PENSION = re.compile(r"\b(pensioned|retired from stud|retires from stud|stud career ends|no longer stand|won't stand|will not stand)\b", re.I)
EXPORT = re.compile(r"\b(exported|sold to (japan|korea|turkey|india|brazil|chile|argentina|saudi arabia)|heads to (japan|korea|turkey|india))\b", re.I)
MOVE = re.compile(r"\b(relocates?|relocated|moves to|moving to|to stand at|to stand in|will stand at|joins .{0,40} roster|acquires)\b", re.I)
# a name right after these is someone's relative, not the subject ("Blue Bresil, sire of X, dies")
RELATIVE = re.compile(r"\b(SIRE|DAM|SON|DAUGHTER|BROTHER|SISTER|BY|OUT) OF $|\b(BY|OUT OF) $")
TDN_SITEMAP = "https://www.thoroughbreddailynews.com/sitemap-posttype-post.{year}.xml"
CRAWL_DELAY = 10  # thoroughbreddailynews.com/robots.txt


def fetch(url: str) -> list[dict]:
    # Intentionally off. See crossr_pipeline/collection.py.
    from crossr_pipeline.collection import refuse_if_off
    refuse_if_off("Stallion news watch")

    req = urllib.request.Request(url, headers={"User-Agent": "Crossr/1.0 (daily stallion news check)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        root = ET.fromstring(resp.read())
    items = []
    for it in root.findall(".//item"):
        when = it.findtext("pubDate") or ""
        try:
            when = parsedate_to_datetime(when).isoformat()
        except (TypeError, ValueError):
            pass
        items.append({"title": (it.findtext("title") or "").strip(), "link": (it.findtext("link") or "").strip(),
                      "published": when})
    return items


def classify(title: str) -> str | None:
    if DEATH.search(title):
        return "deceased"
    if PENSION.search(title):
        return "pensioned"
    if EXPORT.search(title):
        return "exported"
    if MOVE.search(title):
        return "relocated"
    return None


def _status_at(title: str) -> int:
    """Where the status word starts in the (name-key style) headline."""
    for rx in (DEATH, PENSION, EXPORT, MOVE):
        m = rx.search(title)
        if m:
            return m.start()
    return -1


def matches(items: list[dict], names: dict[str, tuple[str, int | None]]) -> list[dict]:
    """Stories whose headline has a status word and names a registry stallion (longest name wins)."""
    out = []
    ordered = sorted(names, key=len, reverse=True)
    for it in items:
        status = classify(it["title"])
        if not status:
            continue
        head = ss.name_key(it["title"]) + " "
        cut = _status_at(head)
        for key in ordered:
            # the subject: named before the status word, and not as someone's sire / dam
            m = re.search(rf"(?<![A-Z0-9]){re.escape(key)}(?![A-Z0-9])", head)
            if m and (cut < 0 or m.start() < cut) and not RELATIVE.search(head[:m.start()]):
                display, year = names[key]
                out.append({**it, "name_key": key, "name": display, "foal_year": year, "status": status})
                break
    return out




def registry_names() -> dict[str, tuple[str, int | None]]:
    """Every stallion on a stud card or the 2026 mares-bred list (worldwide, so a scope switch loses nothing)."""
    from crossr_core import sample_db

    names = {}
    for display, card in sample_db.stallion_roster_from_fees().items():
        names.setdefault(ss.name_key(display), (display, card.get("Year Born") or None))
    for row in sample_db.load_table("breeding_seasons"):
        if str(row.get("breeding_year")) == "2026" and row.get("stallion"):
            names.setdefault(ss.name_key(row["stallion"]), (row["stallion"], None))
    return {k: v for k, v in names.items() if len(k) >= 3}


def archive(since: int, until: int) -> list[dict]:
    """Every TDN article headline from the yearly sitemaps (allowed by robots.txt; article pages are not opened).

    The headline is read from the article's address: /war-front-pensioned-at-claiborne/.
    """
    # Intentionally off. See crossr_pipeline/collection.py.
    from crossr_pipeline.collection import refuse_if_off
    refuse_if_off("Stallion news archive")

    items = []
    for year in range(until, since - 1, -1):
        req = urllib.request.Request(TDN_SITEMAP.format(year=year), headers={"User-Agent": "Crossr/1.0 (stallion news archive)"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            text = resp.read().decode("utf-8", "replace")
        for loc, mod in re.findall(r"<loc>([^<]+)</loc>\s*(?:<lastmod>([^<]*)</lastmod>)?", text):
            slug = loc.rstrip("/").rsplit("/", 1)[-1]
            items.append({"title": slug.replace("-", " "), "link": loc, "published": mod or str(year)})
        print(f"  {year}: {len(items)} headlines so far", flush=True)
        time.sleep(CRAWL_DELAY)
    return items


def current_registry_names() -> dict[str, tuple[str, int | None]]:
    """Stallions on a current card anywhere (this or last season) plus 2026 breeders."""
    from crossr_core import sample_db

    names = {}
    year = __import__("datetime").date.today().year
    for display, card in sample_db.stallion_roster_from_fees().items():
        try:
            latest = int(str(card.get("Latest Season") or "")[:4])
        except ValueError:
            continue
        if latest >= year - 1:
            names.setdefault(ss.name_key(display), (display, card.get("Year Born") or None))
    for row in sample_db.load_table("breeding_seasons"):
        if str(row.get("breeding_year")) == str(year) and row.get("stallion"):
            names.setdefault(ss.name_key(row["stallion"]), (row["stallion"], None))
    return {k: v for k, v in names.items() if len(k) >= 4}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--archive", action="store_true", help="scan TDN's yearly article sitemaps instead of the feed")
    ap.add_argument("--since", type=int, default=2018, help="first year for --archive")
    args = ap.parse_args()
    if args.archive:
        year = __import__("datetime").date.today().year
        items = archive(args.since, year)
        found = matches(items, current_registry_names())
        # one suggestion per stallion and kind: the newest story
        newest = {}
        for f in sorted(found, key=lambda f: f["published"], reverse=True):
            newest.setdefault((f["name_key"], f["status"]), f)
        found = sorted(newest.values(), key=lambda f: (f["status"], f["name"]))
        print(f"{len(items)} headlines read, {len(found)} stallion/news pairs")
        for f in found:
            print(f"  {f['status']:9} {f['name']}: {f['published'][:10]} {f['link']}")
        _store(found, args.apply)
        return
    items = [it for url in FEEDS for it in fetch(url)]
    found = matches(items, registry_names())
    print(f"{len(items)} stories read, {len(found)} mention a registry stallion with a status word")
    for f in found:
        print(f"  {f['status']:9} {f['name']}: {f['title']}  {f['link']}")
    _store(found, args.apply)


def _store(found: list[dict], apply: bool) -> None:
    if not apply:
        print("dry run: nothing stored (use --apply)")
        return
    from crossr_core import railway_db

    with railway_db.connect() as conn:
        conn.execute(ss.SUGGESTIONS_SCHEMA)
        new = 0
        for f in found:
            new += conn.execute(
                """INSERT INTO stallion_status_suggestions (name_key, foal_year, status, headline, url, published)
                   VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                (f["name_key"], f["foal_year"], f["status"], f["title"], f["link"], f["published"])).rowcount
        print(f"stored {new} new suggestion(s); review with: python3 scripts/stallion_status.py suggestions")


if __name__ == "__main__":
    main()

"""NYRA race entries -> race_entries (daily).

NYRA publishes the entries for Belmont Park, Saratoga and Aqueduct on nyra.com
as server-rendered HTML (posted 3-4 days before race day). nyra.com has no
robots.txt restrictions and its Terms & Conditions have no clause against
automated reading. We read it politely: plain HTTP with an honest User-Agent,
one request at a time with a pause between them, only the small per-race
fragment (``/<site>/rdl/race/``), and stop on any 403/429. No anti-bot
measure is worked around: if NYRA starts refusing, the job stops and logs it.

Each runner carries its Equibase refno (NYRA links to the Equibase profile),
so horses are linked by identity, not name. Run:

    python -m crossr_pipeline entries [--apply] [--days 7] [--site belmont]

A card that is re-read updates in place; runners that drop off a re-read race
are marked scratched. After writing, this week's stored entries list
(weekly_reports) is refreshed so cards drawn midweek show up on it.
"""

from __future__ import annotations

import datetime as dt
import html as htmlmod
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

BASE = "https://www.nyra.com"
SITES = ("belmont", "saratoga", "aqueduct")
SOURCE = "nyra"
USER_AGENT = "CrossrEntries/1.0 (weekly entries list for a private breeding-analytics site)"
DELAY_S = 5.0
JOB = "entries-nyra"
# Equibase track codes as race_starts stores them
VENUES = {"BELMONT PARK": "BEL", "SARATOGA": "SAR", "AQUEDUCT": "AQU", "BELMONT AT THE BIG A": "BAQ",
          "BELMONT AT SARATOGA": "SAR"}
SITE_DEFAULT = {"belmont": ("BEL", "Belmont Park"), "saratoga": ("SAR", "Saratoga"), "aqueduct": ("AQU", "Aqueduct")}


class Refused(RuntimeError):
    """NYRA answered 403/429: stop for today, do not retry harder."""


def _ssl_context():
    """python.org builds ship without a CA bundle; use certifi's when installed."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch(url: str, timeout: float = 20) -> str:
    # Intentionally off. See crossr_pipeline/collection.py.
    from crossr_pipeline.collection import refuse_if_off
    refuse_if_off("NYRA entries")

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            return resp.read(2_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise Refused(f"{e.code} from {url}") from e
        if e.code == 404:
            return ""
        raise


# ----------------------------------------------------------------- parsing
def _text(fragment: str) -> str:
    t = re.sub(r"<[^>]+>", " ", fragment or "")
    return re.sub(r"\s+", " ", htmlmod.unescape(t)).strip()


def race_days(page: str) -> list[str]:
    """Dates offered under 'Upcoming' on an entries page (YYYY-MM-DD)."""
    return sorted(set(re.findall(r"[?&]day=(\d{4}-\d{2}-\d{2})&(?:amp;)?limit=entries", page)))


def race_numbers(page: str, day: str) -> list[int]:
    nums = re.findall(r"day=" + re.escape(day) + r"&(?:amp;)?limit=entries&(?:amp;)?race=(\d+)", page)
    return sorted({int(n) for n in nums})


def _upcoming_days(page: str) -> list[str]:
    """Day labels in the 'Upcoming' list, e.g. 'Thursday, November 5' (empty when nothing is drawn)."""
    m = re.search(r">\s*Upcoming\s*<(.*?)(?:>\s*Race\s*<|$)", page, re.S)
    return re.findall(r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day, [A-Z][a-z]+ \d{1,2}", _text(m.group(1))) if m else []


def parse_race(page: str, day: str, site: str) -> Optional[dict]:
    """One race fragment -> {race_number, race_type, race_name, distance, surface, track_code, track, runners}."""
    m = re.search(r"<header[^>]*>\s*Race\s+(\d+)\s*</header>(.*?)(?=<div class=\"space-y-3\.5\">|$)", page, re.S)
    if not m:
        return None
    number, head = int(m.group(1)), m.group(2)
    sections = re.findall(r"<section[^>]*>(.*?)</section>", head, re.S)
    divs = lambda s: [_text(d) for d in re.findall(r"<div[^>]*>(.*?)</div>", s, re.S)]
    first = [d for d in divs(sections[0])] if sections else []
    second = divs(sections[1]) if len(sections) > 1 else []
    race_type = re.sub(r"^\$[\d,]+\s*", "", first[0]).strip() if first else ""
    distance = second[0] if second else ""
    surface = second[1] if len(second) > 1 else ""
    venue = re.sub(r"^.*?\bat\b\s*", "", second[-1]).strip() if second else ""
    code, track = SITE_DEFAULT.get(site, ("", ""))
    if venue:
        code, track = VENUES.get(venue.upper(), code), venue
    name_m = re.search(r"<header class=\"font-semibold text-lg[^>]*>(.*?)</header>", head, re.S)
    race_name = _text(name_m.group(1)) if name_m else ""
    runners = []
    for block in re.split(r"<hr\b[^>]*>", page[m.end():]):
        # only the runner's own row (the last block runs on into the page footer)
        own = re.search(r"<div class=\"flex items-start.*?Morning Line Odds\"[^<]*</div></div></div>", block, re.S)
        block = own.group(0) if own else block[:3000]
        a = re.search(r"refno=(\d+)[^>]*>(.*?)</a>", block, re.S)
        post = re.search(r"saddle-[^\"]*\"[^>]*>\s*([0-9]+[A-Z]?)\s*<", block)
        if not a:
            continue
        info = re.findall(r"<div class=\"text-zinc-800[^\"]*\">(.*?)</div>", block, re.S)
        age_sex = _text(info[-1]).split("•")[-1].strip() if info else ""
        age = re.match(r"(\d{1,2})\s*/", age_sex)
        scratched = bool(re.search(r"scratch|line-through|\bSCR\b", block, re.I))
        runners.append({
            "horse": _text(a.group(2)),
            "horse_refno": a.group(1),
            "post_position": post.group(1) if post else "",
            "foal_year": int(day[:4]) - int(age.group(1)) if age else None,
            "status": "scratched" if scratched else "entered",
        })
    return {"race_number": number, "race_type": race_type, "race_name": race_name, "distance": distance,
            "surface": surface, "track_code": code, "track": track, "runners": runners}


def rows_for_race(race: dict, day: str) -> list[dict]:
    out = []
    for r in race["runners"]:
        out.append({
            "race_date": day, "track_code": race["track_code"], "track": race["track"], "country": "USA",
            "race_number": race["race_number"], "horse": r["horse"], "horse_refno": r["horse_refno"],
            "foal_year": r["foal_year"], "race_type": race["race_type"] or None,
            "race_name": race["race_name"] or None, "distance": race["distance"] or None,
            "surface": race["surface"] or None, "post_position": r["post_position"] or None,
            "status": r["status"],
            "source_id": f"nyra:{race['track_code']}:{day}:{race['race_number']}:{r['horse_refno']}",
        })
    return out


# ----------------------------------------------------------------- crawl
def crawl(sites=SITES, days_ahead: int = 7, today: Optional[dt.date] = None, get: Callable[[str], str] = fetch,
          delay: float = DELAY_S, log=print) -> list[tuple[str, dict]]:
    """[(day, race)] for every drawn race in the next `days_ahead` days. Stops on a refusal."""
    today = today or dt.date.today()
    last = (today + dt.timedelta(days=days_ahead)).isoformat()
    out: list[tuple[str, dict]] = []
    first_request = True
    seen: set[tuple[str, str]] = set()

    def polite(url: str) -> str:
        nonlocal first_request
        if not first_request:
            time.sleep(delay)
        first_request = False
        return get(url)

    for site in sites:
        index = polite(f"{BASE}/{site}/racing/entries/")
        if not index or not _upcoming_days(index):
            log(f"{site}: no upcoming race days posted")
            continue
        for day in race_days(index):
            if not (today.isoformat() <= day <= last):
                continue
            first_page = polite(f"{BASE}/{site}/rdl/race/?day={day}&limit=entries&race=1")
            numbers = race_numbers(first_page, day) or ([1] if first_page else [])
            race = parse_race(first_page, day, site)
            if not race or not race["runners"]:
                log(f"{site} {day}: no entries drawn yet")
                continue
            if (day, race["track_code"]) in seen:  # NYRA's sites share one card
                continue
            seen.add((day, race["track_code"]))
            out.append((day, race))
            for n in numbers:
                if n == 1:
                    continue
                race = parse_race(polite(f"{BASE}/{site}/rdl/race/?day={day}&limit=entries&race={n}"), day, site)
                if race and race["runners"]:
                    out.append((day, race))
            log(f"{site} {day}: {len(numbers)} race(s)")
    return out


def run(apply: bool = False, days_ahead: int = 7, sites=SITES, get: Callable[[str], str] = fetch,
        delay: float = DELAY_S, conn=None, today: Optional[dt.date] = None, log=print) -> dict:
    from crossr_core import entries

    try:
        races = crawl(sites, days_ahead, today=today, get=get, delay=delay, log=log)
        refused = None
    except Refused as e:
        races, refused = [], str(e)
        log(f"stopped: NYRA refused the request ({e}); not retrying")
    rows = [row for day, race in races for row in rows_for_race(race, day)]
    summary = {"races": len(races), "rows": len(rows), "refused": refused}
    if conn is None:
        from crossr_core import railway_db
        conn_ctx = railway_db.connect()
    else:
        from contextlib import nullcontext
        conn_ctx = nullcontext(conn)
    with conn_ctx as c:
        from crossr_pipeline import state
        state.ensure(c)
        logged = state.Run(c, JOB) if apply else None
        counts = entries.upsert(c, rows, SOURCE)
        scratched = 0
        for day, race in races:
            keys = {entries.weekly.name_key(r["horse"]) for r in race["runners"]}
            scratched += entries.mark_missing_scratched(c, SOURCE, day, race["track_code"], race["race_number"], keys)
        summary.update(counts, scratched_by_absence=scratched)
        unlinked = c.execute("SELECT count(*) FROM race_entries_unlinked").fetchone()[0]
        summary["unlinked_horses"] = unlinked
        if apply:
            summary["week_list_rows"] = entries.refresh_week_report(c, today)
            logged.bump("races", len(races))
            logged.bump("rows", len(rows))
            logged.finish("partial" if refused else "ok",
                          f"{len(races)} races, {len(rows)} runners, {counts['linked']} linked, {unlinked} to enrich")
            c.commit()
        else:
            c.rollback()
    log(("stored: " if apply else "dry run (nothing written): ") + ", ".join(f"{k}={v}" for k, v in summary.items()))
    return summary


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--site", action="append", choices=SITES)
    ap.add_argument("--delay", type=float, default=DELAY_S)
    a = ap.parse_args(argv)
    run(apply=a.apply, days_ahead=a.days, sites=tuple(a.site or SITES), delay=a.delay)
    return 0


if __name__ == "__main__":
    sys.exit(main())

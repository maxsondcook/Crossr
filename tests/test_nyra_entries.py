"""NYRA entries adapter (crossr_pipeline.nyra_entries) and race_entries writes (crossr_core.entries).

Parsing tests use a synthetic page shaped like nyra.com's race fragment (made-up
horses). The database tests run only against crossr_dev, inside a transaction
that is rolled back.
"""

import datetime as dt
import os

import pytest

from crossr_core import entries, weekly
from crossr_pipeline import nyra_entries as nyra


def runner(name, refno, post, age_sex="3/C", odds="5/1", extra=""):
    return f"""
<div class="flex items-start gap-3 lg:gap-5 text-sm {extra}"><div class="order-3 flex-1 leading-none"><div class="font-semibold text-lg lg:text-2xl -mt-1 mb-1 leading-tight blend-links"><a href="http://www.equibase.com/profiles/Results.cfm?type=Horse&amp;registry=T&amp;refno={refno}" target="equibase-horse-x">
                {name}
            </a></div><div class="text-zinc-800 dark:text-white">A Jockey &bull; B Trainer</div><div class="text-zinc-800 dark:text-white mt-1 text-xs lg:text-sm">124lbs &bull; {age_sex}</div></div><div class="order-1 pt-1 lg:pt-0 relative -top-2.5 lg:top-0"><div class="w-9 h-7 saddle-{post} font-semibold flex items-center justify-center rounded-md">
    {post}
</div></div><div class="order-5 leading-none text-right"><div class="font-semibold" title="Current Odds">{odds}</div><div class="text-zinc-800 dark:text-white" title="Morning Line Odds">ML {odds}</div></div></div>
    <hr class="border-0 border-t">"""


def race_page(day="2026-11-07", number=8, runners=None, venue="Belmont Park", name="Test Stakes", races=10):
    tabs = "".join(f'<a href="./?day={day}&amp;limit=entries&amp;race={n}">{n}</a>' for n in range(1, races + 1))
    runners = runners if runners is not None else [runner("Alpha Star", "90000001", 1), runner("Beta Wave", "90000002", 2),
                                                   runner("Gamma Ray (IRE)", "90000003", 3, age_sex="4/G")]
    return f"""<nav>{tabs}</nav>
<div class="py-7 lg:pr-12 space-y-6 swap:fade transition-all">
    <div class="text-sm lg:text-base flex flex-col lg:flex-row items-baseline gap-3 lg:gap-5">
        <header class="text-3xl lg:text-5xl font-semibold font-heading">
            Race {number}
        </header>
        <section class="flex items-baseline gap-5"><div>
                $200,000
                Stakes
            </div></section>
        <section class="flex-1 flex items-baseline gap-5 -mt-2 lg:mt-0">
            <div class="text-zinc-800 dark:text-white" title="One Mile">1M</div>
            <div class="text-zinc-800 dark:text-white">
                Dirt
            </div>
            <div class="text-zinc-800 dark:text-white">
            </div>
            <div class="text-zinc-800 dark:text-white ml-auto">
                3:12p at
                {venue}
            </div>
        </section>
    </div>
    <div class="text-sm lg:text-base text-zinc-800 dark:text-white">
        <header class="font-semibold text-lg lg:text-xl text-black dark:text-white mb-2">
            {name}
        </header>
        Exacta ($1)
    </div>
<div class="space-y-3.5">{''.join(runners)}</div>
<footer>Talking Horses | Scratches &amp; Changes | Entries</footer>"""


INDEX = """<a href="./?day=2026-11-05&amp;limit=entries">5</a><a href="./?day=2026-11-07&amp;limit=entries">7</a>
<a href="./?day=2026-11-29&amp;limit=entries">29</a>
<div><span>Upcoming</span></div><div>Thursday, November 5</div><div>Saturday, November 7</div><div>Race</div>"""


# ------------------------------------------------------------------ parsing
def test_parse_race_fields_and_runners():
    race = nyra.parse_race(race_page(), "2026-11-07", "belmont")
    assert race["race_number"] == 8 and race["race_type"] == "Stakes" and race["race_name"] == "Test Stakes"
    assert (race["distance"], race["surface"], race["track_code"], race["track"]) == ("1M", "Dirt", "BEL", "Belmont Park")
    assert [r["horse"] for r in race["runners"]] == ["Alpha Star", "Beta Wave", "Gamma Ray (IRE)"]
    assert [r["horse_refno"] for r in race["runners"]] == ["90000001", "90000002", "90000003"]
    assert [r["post_position"] for r in race["runners"]] == ["1", "2", "3"]
    assert [r["foal_year"] for r in race["runners"]] == [2023, 2023, 2022]
    # the footer's "Scratches & Changes" must not scratch the last runner
    assert {r["status"] for r in race["runners"]} == {"entered"}


def test_scratched_runner_and_venue_mapping():
    page = race_page(venue="Saratoga", runners=[runner("Alpha Star", "90000001", 1),
                                                runner("Beta Wave", "90000002", 2, odds="SCR", extra="line-through")])
    race = nyra.parse_race(page, "2026-08-01", "belmont")
    assert race["track_code"] == "SAR"
    assert [r["status"] for r in race["runners"]] == ["entered", "scratched"]


def test_index_days_and_race_numbers():
    assert nyra.race_days(INDEX) == ["2026-11-05", "2026-11-07", "2026-11-29"]
    assert nyra._upcoming_days(INDEX) == ["Thursday, November 5", "Saturday, November 7"]
    assert nyra._upcoming_days("<div>No upcoming race days</div>") == []
    assert nyra.race_numbers(race_page(races=9), "2026-11-07") == list(range(1, 10))


def test_rows_have_stable_source_ids():
    race = nyra.parse_race(race_page(), "2026-11-07", "belmont")
    rows = nyra.rows_for_race(race, "2026-11-07")
    assert rows[0]["source_id"] == "nyra:BEL:2026-11-07:8:90000001"
    assert len({r["source_id"] for r in rows}) == len(rows)


def test_crawl_is_polite_dedupes_shared_cards_and_stops_on_refusal():
    calls = []

    def get(url):
        calls.append(url)
        if url.endswith("/racing/entries/"):
            return INDEX
        day = url.split("day=")[1][:10]
        n = int(url.rsplit("race=", 1)[1])
        if day == "2026-11-07":
            return race_page(day=day, number=n, races=2)
        return ""  # 11-05: not drawn yet

    races = nyra.crawl(("belmont", "saratoga"), days_ahead=7, today=dt.date(2026, 11, 4), get=get, delay=0, log=lambda m: None)
    assert [(d, r["race_number"]) for d, r in races] == [("2026-11-07", 1), ("2026-11-07", 2)]
    assert not any("2026-11-29" in u for u in calls)  # outside the window
    # saratoga's site shows the same Belmont card: read race 1 to learn that, then skip the rest
    assert sum("saratoga/rdl" in u and "2026-11-07" in u for u in calls) == 1

    def refuse(url):
        raise nyra.Refused("403")

    with pytest.raises(nyra.Refused):
        nyra.crawl(("belmont",), get=refuse, delay=0, log=lambda m: None)


# ------------------------------------------------------------------ database (crossr_dev only)
def _dev_db():
    url = os.environ.get("DATABASE_URL", "")
    return url.rsplit("/", 1)[-1].split("?")[0] == "crossr_dev"


@pytest.fixture
def conn():
    if not _dev_db():
        pytest.skip("needs DATABASE_URL pointing at crossr_dev")
    from crossr_core import railway_db

    with railway_db.connect() as c:
        yield c
        c.rollback()


def _horse(c, hid, name, refno, fy):
    c.execute("""INSERT INTO race_horses (id, display_name, name_key, equibase_refno, foal_year, status)
                 VALUES (%s, %s, %s, %s, %s, 'ok')""", (hid, name, weekly.name_key(name), refno, fy))


def _entry(name, refno, fy, rn=3, date="2026-11-07", status="entered"):
    return {"race_date": date, "track_code": "bel", "track": "Belmont Park", "race_number": rn, "horse": name,
            "horse_refno": refno, "foal_year": fy, "status": status, "source_id": f"t:{refno}"}


def test_db_namesakes_are_linked_by_refno_never_by_name(conn):
    _horse(conn, "zz-test-1", "Zz Namesake", "99000001", "2015")
    _horse(conn, "zz-test-2", "Zz Namesake", "99000002", "2022")
    entries.upsert(conn, [_entry("Zz Namesake", "99000002", 2022)], "test")
    got = conn.execute("SELECT horse_id FROM race_entries WHERE horse_key = 'ZZ NAMESAKE'").fetchall()
    assert got == [("zz-test-2",)]
    # a third namesake we don't have yet: stays unlinked, never grabs one of the two above
    entries.upsert(conn, [_entry("Zz Namesake", "99000003", 2023, rn=5)], "test")
    got = conn.execute("SELECT horse_id FROM race_entries WHERE horse_key = 'ZZ NAMESAKE' AND race_number = 5").fetchone()
    assert got == (None,)
    assert conn.execute("SELECT count(*) FROM race_entries_unlinked WHERE horse_refno = '99000003'").fetchone()[0] == 1


def test_db_reimport_updates_in_place_relinks_and_scratches(conn):
    rows = [_entry("Zz Runner A", "99000011", 2023), _entry("Zz Runner B", "99000012", 2023)]
    entries.upsert(conn, rows, "test")
    entries.upsert(conn, rows, "test")  # same card read twice
    n = conn.execute("SELECT count(*) FROM race_entries WHERE horse_key LIKE 'ZZ RUNNER %'").fetchone()[0]
    assert n == 2
    assert conn.execute("SELECT horse_id FROM race_entries WHERE horse_key = 'ZZ RUNNER A'").fetchone() == (None,)
    _horse(conn, "zz-test-a", "Zz Runner A", "99000011", "2023")  # the pipeline scrapes it later
    counts = entries.upsert(conn, rows[1:], "test")
    assert counts["relinked"] >= 1
    assert conn.execute("SELECT horse_id FROM race_entries WHERE horse_key = 'ZZ RUNNER A'").fetchone() == ("zz-test-a",)
    # B is re-read alone: A dropped off the card
    assert entries.mark_missing_scratched(conn, "test", "2026-11-07", "BEL", 3, {"ZZ RUNNER B"}) == 1
    assert entries.mark_missing_scratched(conn, "test", "2026-11-07", "BEL", 3, set()) == 0  # failed read
    st = dict(conn.execute("SELECT horse_key, status FROM race_entries WHERE horse_key LIKE 'ZZ RUNNER %'").fetchall())
    assert st == {"ZZ RUNNER A": "scratched", "ZZ RUNNER B": "entered"}
    week = weekly.load_entries(conn, dt.date(2026, 11, 2), dt.date(2026, 11, 9))
    assert "ZZ RUNNER A" not in {r["horse_key"] for r in week}


def test_db_undated_placeholder_is_not_a_match_when_the_year_is_known(conn):
    conn.execute("""INSERT INTO race_horses (id, display_name, name_key, status) VALUES ('zz-test-p', 'Zz Old Name', 'ZZ OLD NAME', 'ok')""")
    entries.upsert(conn, [_entry("Zz Old Name", "99000021", 2023)], "test")
    assert conn.execute("SELECT horse_id FROM race_entries WHERE horse_key = 'ZZ OLD NAME'").fetchone() == (None,)
    # a CSV row with no year or refno still links to the one horse of that name
    entries.upsert(conn, [_entry("Zz Old Name", None, None, rn=6)], "test")
    assert conn.execute("SELECT horse_id FROM race_entries WHERE horse_key = 'ZZ OLD NAME' AND race_number = 6").fetchone() == ("zz-test-p",)

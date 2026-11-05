"""Fixture tests for the bug classes that have already shown up in CROSSR.

No database, no network, no scrapers. Each test builds the horse it needs and
calls the same functions the API uses. A blank or nothing is the right answer
when the only match would be a different horse.

Run with scrapers off (this is what the daily workflow runs)::

    DATABASE_URL= CROSSR_SCRAPERS=off python3 -m pytest -q tests/test_bug_regressions.py
"""

from __future__ import annotations

import importlib.util
import socket
import urllib.request
from pathlib import Path

import pytest

from crossr_core import horses, identity, stallion_status, upcoming
import hypomating_engine
import main

_MERGE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "merge_duplicate_race_horses.py"
_spec = importlib.util.spec_from_file_location("merge_duplicate_race_horses", _MERGE_PATH)
merge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(merge)


@pytest.fixture(autouse=True)
def scrapers_off_and_offline(monkeypatch):
    """The suite refuses a live database or an outbound connection."""
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("CROSSR_SCRAPERS", "off")
    attempted = []

    def blocked(*args, **kwargs):
        attempted.append((args, kwargs))
        raise AssertionError("bug regression suite must not use the network")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    yield
    assert attempted == []


def _pedigree(name, sire=None, dam=None):
    tree = {"Horse": name}
    if sire:
        tree["Sire"] = sire if isinstance(sire, dict) else {"Horse": sire}
    if dam:
        tree["Dam"] = dam if isinstance(dam, dict) else {"Horse": dam}
    return tree


def _card(**extra):
    card = {
        "Stud Fee": 10000,
        "Stud Fee Display": "$10,000",
        "Status": "active",
        "Year Born": 2014,
        "Latest Season": 2026,
        "Stud Duty Year": 2018,
        "Farm": "Mill Ridge Farm, KY",
        "Stud Fee Currency": "USD",
        "Surface": "Turf",
    }
    card.update(extra)
    return card


@pytest.fixture
def quiet_profile(monkeypatch):
    """Profile assembly without race, book, or ranking tables."""
    monkeypatch.setattr(horses, "race_results_for", lambda *a, **k: ([], [], []))
    monkeypatch.setattr(horses, "female_family", lambda *a, **k: [])
    monkeypatch.setattr(horses, "load_book_stats", lambda: ({}, {}))
    monkeypatch.setattr(horses, "top_progeny_for_sire", lambda *a, **k: [])
    monkeypatch.setattr(horses, "broodmare_sire_history", lambda *a, **k: [])
    monkeypatch.setattr(horses, "stallion_ranking_history", lambda *a, **k: {"lists": [], "rows": {}})
    monkeypatch.setattr(horses, "stud_book_history", lambda *a, **k: [])
    monkeypatch.setattr(horses, "progeny_stats_from_rankings", lambda *a, **k: {})
    monkeypatch.setattr("crossr_core.sample_db.breeding_for_stallion", lambda *a, **k: [])
    monkeypatch.setattr(identity, "card_identities", lambda: {})
    monkeypatch.setattr(identity, "offspring_counts", lambda facts: (0, 0))
    monkeypatch.setattr(stallion_status, "overrides", lambda: {})


# ---------------------------------------------------------------------------
# Namesake mix-ups: show nothing rather than the wrong horse
# ---------------------------------------------------------------------------

def test_bare_name_shows_neither_namesake(quiet_profile, monkeypatch):
    monkeypatch.setattr(main, "PEDIGREE_DATABASE", {
        "ENGLISHMAN (2002)": _pedigree("Englishman (2002)", "Gentlemen", "A Lady"),
        "ENGLISHMAN (2023)": _pedigree("Englishman (2023)", "Maxfield", "Another Mare"),
    })
    profile = horses.get_horse_profile("Englishman", profiles={"Englishman": _card(**{"Year Born": 2002})})
    assert profile["ambiguous"] is True
    assert profile["years"] == ["2002", "2023"]
    assert "stallion" not in profile
    assert "pedigree" not in profile


def test_young_namesake_does_not_inherit_the_stallion_card(quiet_profile, monkeypatch):
    monkeypatch.setattr(main, "PEDIGREE_DATABASE", {
        "ENGLISHMAN (2002)": _pedigree("Englishman (2002)", "Gentlemen", "A Lady"),
        "ENGLISHMAN (2023)": _pedigree("Englishman (2023)", "Maxfield", "Another Mare"),
    })
    profile = horses.get_horse_profile(
        "Englishman (2023)",
        profiles={"Englishman": _card(**{"Year Born": 2002, "Stud Fee": 5000, "Stud Fee Display": "$5,000"})},
    )
    assert profile["ambiguous"] is False
    assert profile["stallion"] is None
    assert profile["pedigree"]["sire"]["name"] == "Maxfield"
    assert profile["pedigree"]["sire"]["name"] != "Gentlemen"


def test_unknown_name_is_not_a_page(quiet_profile, monkeypatch):
    monkeypatch.setattr(main, "PEDIGREE_DATABASE", {})
    monkeypatch.setattr(horses, "build_stallion_roster", lambda profiles=None: [])
    assert horses.get_horse_profile("Not A Horse", profiles={}) is None


# ---------------------------------------------------------------------------
# Wrong parents (Oscar Performance listed with Cyrano de Bergerac's parents)
# ---------------------------------------------------------------------------

OSCAR_ROWS = [
    (2014, "Kitten's Joy", "Devine Actress"),
    (1998, "Cyrano de Bergerac", "Wrong Dam"),
]


def test_parents_follow_the_foaling_year_or_nothing():
    assert horses.parents_for(OSCAR_ROWS, 2014) == ("Kitten's Joy", "Devine Actress")
    assert horses.parents_for(OSCAR_ROWS, 1998) == ("Cyrano de Bergerac", "Wrong Dam")
    assert horses.parents_for(OSCAR_ROWS, None) == (None, None)
    assert horses.parents_for(OSCAR_ROWS, 2002) == (None, None)


def test_directory_parents_are_the_stallions_not_the_namesakes(monkeypatch):
    horses._STALLION_ROSTER = None
    monkeypatch.setattr(horses, "_parent_lookup", lambda: {"OSCAR PERFORMANCE": OSCAR_ROWS})
    monkeypatch.setattr(horses, "_load_mares_bred_2026", lambda: [
        {"name": "Oscar Performance", "key": "OSCAR PERFORMANCE", "mares_bred": 80, "state": "KY"},
    ])
    monkeypatch.setattr(horses, "_rank_map", lambda: {})
    monkeypatch.setattr("crossr_core.sample_db.table_version", lambda table: 1.0)
    monkeypatch.setattr("crossr_core.sample_db._foal_years_for", lambda names: None)
    monkeypatch.setattr("crossr_core.sample_db.stallion_foal_year", lambda name, year=2026: None)
    monkeypatch.setattr(stallion_status, "overrides", lambda: {})
    roster = horses.build_stallion_roster({"Oscar Performance": _card(**{"Year Born": 2014})})
    oscar = next(row for row in roster if row["name"] == "Oscar Performance")
    assert oscar["sire"] == "Kitten's Joy"
    assert oscar["dam"] == "Devine Actress"
    assert "Cyrano" not in (oscar["sire"] or "")


def test_directory_with_no_year_does_not_guess_a_namesakes_parents(monkeypatch):
    horses._STALLION_ROSTER = None
    monkeypatch.setattr(horses, "_parent_lookup", lambda: {"OSCAR PERFORMANCE": OSCAR_ROWS})
    monkeypatch.setattr(horses, "_load_mares_bred_2026", lambda: [
        {"name": "Oscar Performance", "key": "OSCAR PERFORMANCE", "mares_bred": 80, "state": "KY"},
    ])
    monkeypatch.setattr(horses, "_rank_map", lambda: {})
    monkeypatch.setattr("crossr_core.sample_db.table_version", lambda table: 2.0)
    monkeypatch.setattr("crossr_core.sample_db._foal_years_for", lambda names: None)
    monkeypatch.setattr("crossr_core.sample_db.stallion_foal_year", lambda name, year=2026: None)
    monkeypatch.setattr(stallion_status, "overrides", lambda: {})
    roster = horses.build_stallion_roster({"Oscar Performance": _card(**{"Year Born": 0})})
    oscar = next(row for row in roster if row["name"] == "Oscar Performance")
    assert oscar["sire"] is None and oscar["dam"] is None


# ---------------------------------------------------------------------------
# Inflated progeny earnings (Magnitude: stakes purses $14.6M, race record $9.63M)
# ---------------------------------------------------------------------------

def test_career_earnings_use_the_race_record_of_this_horse_only(monkeypatch):
    monkeypatch.setattr(horses, "_career_earnings_table", lambda: {
        "MAGNITUDE": [
            ("Not This Time", 2022, 9_630_000),
            ("Some Other Sire", 1999, 14_600_000),
        ],
    })
    assert horses.career_earnings(["Magnitude"], "Not This Time") == {"MAGNITUDE": 9_630_000}


def test_duplicate_season_rows_are_not_added_together(monkeypatch):
    monkeypatch.setattr(horses, "_career_earnings_table", lambda: {
        "MAGNITUDE": [("Not This Time", 2022, 9_630_000), ("Not This Time", 2022, 5_000_000)],
    })
    assert horses.career_earnings(["Magnitude"], "Not This Time")["MAGNITUDE"] == 9_630_000


def test_namesake_earnings_are_omitted(monkeypatch):
    monkeypatch.setattr(horses, "_career_earnings_table", lambda: {
        "MAGNITUDE": [("Some Other Sire", 1999, 14_600_000), ("Another Sire", 2010, 1_000)],
    })
    assert horses.career_earnings(["Magnitude"], "Not This Time") == {}


def test_top_progeny_ignores_summed_stakes_purses(monkeypatch):
    monkeypatch.setattr(hypomating_engine, "top_crosses_payload", lambda *a, **k: {
        "crosses": [{
            "broodmare_sire": "Uncle Mo",
            "winners": [{"name": "Magnitude", "status": "G1W", "dam": "A Mare"}],
        }],
    })
    monkeypatch.setattr(hypomating_engine, "load_stakes_data", lambda *a, **k: [])
    monkeypatch.setattr(horses, "_race_horse_progeny", lambda: {})
    monkeypatch.setattr(horses, "_career_earnings_table", lambda: {
        "MAGNITUDE": [("Not This Time", 2022, 9_630_000)],
    })
    # The old figure: each stakes purse added on, including purses he did not earn.
    monkeypatch.setattr(horses, "_progeny_earnings_lookup", lambda: {"MAGNITUDE": 14_600_000})
    rows = horses.top_progeny_for_sire("Not This Time")
    magnitude = next(row for row in rows if row["name"] == "Magnitude")
    assert magnitude["earnings"] == 9_630_000
    assert magnitude["earnings"] != 14_600_000


# ---------------------------------------------------------------------------
# Dead or pensioned stallions still offered for hypomating
# ---------------------------------------------------------------------------

def _standing(**extra):
    return _card(**{
        "Year Born": 2012,
        "Stud Duty Year": 2017,
        "Stud Fee": 15000,
        "Stud Fee Display": "$15,000",
        "Farm": "Claiborne Farm, KY",
        **extra,
    })


def test_card_text_and_overrides_take_a_stallion_off_hypomating(monkeypatch):
    monkeypatch.setattr(stallion_status, "overrides", lambda: {
        "WOOTTON BASSETT": {"status": "deceased", "foal_year": 2008, "note": "died"},
        "WAR FRONT": {"status": "pensioned", "foal_year": 2002, "note": None},
    })
    died_on_the_card = _standing(**{"Stud Fee Display": "Died 2025", "Notes": ""})
    pensioned_on_the_card = _standing(**{"Stud Fee Display": "Pensioned", "Status": "active"})
    assert not hypomating_engine.get_profile_meta("Frosted", {"Frosted": died_on_the_card})["is_active"]
    assert not hypomating_engine.get_profile_meta("War Front", {"War Front": pensioned_on_the_card})["is_active"]
    assert not hypomating_engine.get_profile_meta(
        "Wootton Bassett", {"Wootton Bassett": _standing(**{"Year Born": 2008})}
    )["is_active"]
    assert not hypomating_engine.get_profile_meta(
        "War Front", {"War Front": _standing(**{"Year Born": 2002, "Stud Fee Display": "$15,000"})}
    )["is_active"]
    # A later horse of the same name is not the one who died.
    assert hypomating_engine.get_profile_meta(
        "Wootton Bassett", {"Wootton Bassett": _standing(**{"Year Born": 2023})}
    )["is_active"]


def test_dead_stallion_with_a_proven_cross_is_not_suggested(monkeypatch):
    monkeypatch.setattr(stallion_status, "overrides", lambda: {})
    monkeypatch.setattr(main, "pedigree_tree", lambda name, pedigree_db=None: {})
    mare = _pedigree(
        "Test Mare (2010)",
        sire=_pedigree("Street Cry (1998)", "Machiavellian (1987)"),
        dam="Vertigineux (1995)",
    )
    foal = _pedigree(
        "Proven Foal (2018)",
        sire="Frosted (2012)",
        dam=_pedigree("A Mare (2012)", "Street Cry (1998)"),
    )
    pedigree_db = {"TEST MARE (2010)": mare, "PROVEN FOAL": foal}
    stakes = [{
        "Horse Name": "Proven Foal",
        "Sex": "c",
        "Grade": "G1",
        "Race Name": "Test Stakes",
        "Race Year": 2021,
        "Place": 1,
        "Purse": "$1,000,000",
        "Distance": "9f (D)",
        "Foaling Year": "2018",
    }]
    monkeypatch.setattr(hypomating_engine, "load_stakes_data", lambda *a, **k: stakes)
    profiles = {
        "Frosted": _standing(**{"Stud Fee Display": "Died 2025"}),
        "Curlin": _standing(**{"Year Born": 2004, "Stud Fee": 25000, "Stud Fee Display": "$25,000"}),
    }
    # The same card without the death notice would be offered. The notice is what removes him.
    living = _standing(**{"Stud Fee Display": "$15,000"})
    assert hypomating_engine.get_profile_meta("Frosted", {"Frosted": living})["is_active"]
    result = hypomating_engine.suggest_matings(pedigree_db, profiles, "Test Mare")
    offered = [row["name"] for row in result["suggestions"]]
    anchors = [row["anchor"] for row in result["lineage_groups"]]
    assert "Frosted" not in offered
    assert "Frosted" not in anchors


def test_directory_omits_pensioned_and_dead(monkeypatch):
    horses._STALLION_ROSTER = None
    monkeypatch.setattr(horses, "_parent_lookup", lambda: {})
    monkeypatch.setattr(horses, "_rank_map", lambda: {})
    monkeypatch.setattr("crossr_core.sample_db.table_version", lambda table: 3.0)
    monkeypatch.setattr("crossr_core.sample_db._foal_years_for", lambda names: None)
    monkeypatch.setattr("crossr_core.sample_db.stallion_foal_year", lambda name, year=2026: None)
    monkeypatch.setattr(stallion_status, "overrides", lambda: {
        "WAR FRONT": {"status": "pensioned", "foal_year": 2002, "note": None},
    })
    monkeypatch.setattr(horses, "_load_mares_bred_2026", lambda: [
        {"name": "Curlin", "key": "CURLIN", "mares_bred": 100, "state": "KY"},
        {"name": "Frosted", "key": "FROSTED", "mares_bred": 40, "state": "KY"},
        {"name": "War Front", "key": "WAR FRONT", "mares_bred": 70, "state": "KY"},
    ])
    profiles = {
        "Curlin": _standing(**{"Year Born": 2004}),
        "Frosted": _standing(**{"Stud Fee Display": "Died 2025"}),
        "War Front": _standing(**{"Year Born": 2002, "Stud Fee Display": "$15,000"}),
    }
    names = {row["name"] for row in horses.build_stallion_roster(profiles)}
    assert names == {"Curlin"}


# ---------------------------------------------------------------------------
# Hip numbers with and without zero-padding
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("a, b", [("35", "0035"), ("035", "35"), ("50a", "0050A"), (" 7 ", "0007")])
def test_padded_hip_numbers_are_the_same_hip(a, b):
    assert upcoming.hip_key(a) == upcoming.hip_key(b)


def test_different_hips_stay_different():
    assert upcoming.hip_key("350") != upcoming.hip_key("0035")
    assert upcoming.hip_key("35A") != upcoming.hip_key("35")


def test_lot_lookup_accepts_either_padding(monkeypatch):
    lots = [{"hip": "0035"}, {"hip": "0035A"}, {"hip": "0350"}]
    monkeypatch.setattr(upcoming, "list_lots", lambda catalog_id: lots)
    assert upcoming.get_lot("keeneland", "35")["hip"] == "0035"
    assert upcoming.get_lot("keeneland", "0035")["hip"] == "0035"
    assert upcoming.get_lot("keeneland", "35a")["hip"] == "0035A"
    assert upcoming.get_lot("keeneland", "350")["hip"] == "0350"
    assert upcoming.get_lot("keeneland", "36") is None


# ---------------------------------------------------------------------------
# Duplicate Equibase ids: mark the copies, do not delete them
# ---------------------------------------------------------------------------

def _race_row(row_id, key, refno="10040120", year="2016", status="ok", starts=4):
    return {
        "id": row_id,
        "pedigree_key": key,
        "name_key": key.split(" |")[0].split(" (")[0],
        "foal_year": year,
        "status": status,
        "fetched_at": "2026-10-20T07:04:59",
        "equibase_refno": refno,
        "seasons": 2,
        "starts": starts,
    }


def _active_duplicate_refnos(rows):
    counts = {}
    for row in rows:
        refno = str(row.get("equibase_refno") or "")
        if not refno or (row.get("status") or "") == "merged":
            continue
        counts[refno] = counts.get(refno, 0) + 1
    return sorted(ref for ref, n in counts.items() if n > 1)


def test_duplicate_equibase_ids_are_marked_merged_and_kept():
    rows = [
        _race_row("1", "CALL PAUL (2016)"),
        _race_row("2", "CALL PAUL | FRIESAN FIRE | AVANI"),
        _race_row("3", "CALL PAUL | FRIESAN FIRE | "),
    ]
    assert _active_duplicate_refnos(rows) == ["10040120"]
    merges, conflicts = merge.plan_merges(rows)
    assert conflicts == []
    drop_ids = {row["id"] for plan in merges for row in plan["drop"]}
    assert drop_ids == {"2", "3"}
    simulated = []
    for row in rows:
        copy = dict(row)
        if copy["id"] in drop_ids:
            copy["status"] = "merged"
        simulated.append(copy)
    assert len(simulated) == len(rows)
    assert all(row["id"] in {r["id"] for r in simulated} for row in rows)
    assert _active_duplicate_refnos(simulated) == []
    assert sum(1 for row in simulated if row["status"] == "ok") == 1


def test_same_equibase_id_with_two_foaling_years_is_not_merged():
    rows = [
        _race_row("5", "Z (2001)", refno="7", year="2001"),
        _race_row("6", "Z (2003)", refno="7", year="2003"),
    ]
    merges, conflicts = merge.plan_merges(rows)
    assert merges == []
    assert [c["refno"] for c in conflicts] == ["7"]
    assert len(rows) == 2


# ---------------------------------------------------------------------------
# Repeated grade labels ("Iroquois Stakes (Gr. 3) G3")
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("race_name, grade, expected", [
    ("Iroquois Stakes (Gr. 3) G3", "3", "Iroquois Stakes"),
    ("Iroquois Stakes (Gr. 3)", "3", "Iroquois Stakes"),
    ("Iroquois Stakes Gr. 3", "G3", "Iroquois Stakes"),
    ("Iroquois Stakes (Gr. 3)", "", "Iroquois Stakes (Gr. 3)"),
])
def test_race_name_does_not_repeat_the_grade_tag(race_name, grade, expected):
    assert horses._race_label(race_name, grade) == expected


def test_start_row_shows_the_grade_once():
    row = horses._start_row(
        "2024-11-01", "CD", "USA", "8", "Iroquois Stakes (Gr. 3) G3", "3", "1", None,
    )
    shown = f"{row['race_name']} {row['class']}"
    assert row["class"] == "G3"
    assert row["race_name"] == "Iroquois Stakes"
    assert shown.lower().count("g3") == 1
    assert "(gr" not in shown.lower()


# ---------------------------------------------------------------------------
# "N/A" shown as a real height or accomplishment
# ---------------------------------------------------------------------------

def _junk(value):
    return isinstance(value, str) and value.strip().lower() in {"n/a", "na", "#n/a", "undefined", "nan", "null", "none"}


def test_missing_height_and_accomplishments_are_blank(quiet_profile, monkeypatch):
    tree = _pedigree("Curlin (2004)", "Smart Strike (1992)", "Sherriff's Deputy (1998)")
    monkeypatch.setattr(main, "PEDIGREE_DATABASE", {"CURLIN (2004)": tree, "CURLIN": tree})
    profile = horses.get_horse_profile("Curlin", profiles={"Curlin": _card(**{
        "Year Born": 2004,
        "Height": "N/A",
        "Major Wins": "N/A",
        "Career Highlight": "#N/A",
        "Race Record": {
            "3YO": {
                "Starts": 5, "1sts": 2, "2nds": 1, "3rds": 0,
                "Earnings": 500000, "Season": 2007,
                "Major Accomplishments": "n/a",
            },
        },
    })})
    stallion = profile["stallion"]
    assert stallion["height"] is None
    assert stallion["major_wins"] is None
    assert stallion["career_highlight"] is None
    assert profile["race_record"][0]["accomplishments"] is None
    assert not any(_junk(season.get("accomplishments")) for season in profile["race_record"])
    assert not _junk(stallion["height"])


def test_a_real_height_and_accomplishment_are_kept(quiet_profile, monkeypatch):
    tree = _pedigree("Curlin (2004)", "Smart Strike (1992)", "Sherriff's Deputy (1998)")
    monkeypatch.setattr(main, "PEDIGREE_DATABASE", {"CURLIN (2004)": tree})
    profile = horses.get_horse_profile("Curlin (2004)", profiles={"Curlin": _card(**{
        "Year Born": 2004,
        "Height": "16.3 hands",
        "Major Wins": "Preakness Stakes",
        "Race Record": {
            "3YO": {
                "Starts": 5, "1sts": 2, "2nds": 1, "3rds": 0,
                "Earnings": 500000, "Season": 2007,
                "Major Accomplishments": "Won the Preakness",
            },
        },
    })})
    assert profile["stallion"]["height"] == "16.3 hands"
    assert profile["stallion"]["major_wins"] == "Preakness Stakes"
    assert profile["race_record"][0]["accomplishments"] == "Won the Preakness"


def test_season_row_does_not_invent_an_accomplishment():
    row = horses._season_row(2024, 2022, {"starts": 4, "firsts": 1, "seconds": 0, "thirds": 0, "earnings": 80000})
    assert row["accomplishments"] is None


# ---------------------------------------------------------------------------
# Run Tiger Run: in the directory, profile was a 404
# ---------------------------------------------------------------------------

def test_run_tiger_run_directory_profile_is_not_a_404(quiet_profile, monkeypatch):
    monkeypatch.setattr(main, "PEDIGREE_DATABASE", {})
    monkeypatch.setattr(horses, "build_stallion_roster", lambda profiles=None: [{
        "name": "Run Tiger Run",
        "key": "RUN TIGER RUN",
        "sire": None,
        "dam": None,
        "farm": "WA",
    }])
    profile = horses.get_horse_profile("Run Tiger Run", profiles={})
    assert profile is not None
    assert profile["ambiguous"] is False
    assert profile["name"] == "Run Tiger Run"
    assert profile["pedigree"] is None
    assert profile["stallion"] is None
    assert profile.get("has_pedigree") is False

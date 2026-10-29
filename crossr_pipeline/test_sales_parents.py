from datetime import datetime, timedelta, timezone
from pathlib import Path

from crossr_pipeline import sales_parents as sp
from equibase_scraper.parse import narrow_yearless, resolve_html

FIXTURES = Path(__file__).resolve().parents[1] / "equibase_scraper" / "fixtures"


def test_yob_window_bounds_parent_age():
    assert sp.yob_window("dam", 2015, 2022) == (1997, 2012)
    assert sp.yob_window("sire", 2010, 2024) == (1994, 2007)
    assert sp.yob_window("dam", None, 2022) is None
    # Foals 30 years apart cannot share a dam.
    assert sp.yob_window("dam", 1990, 2020) is None


def test_pick_row_uses_sire_and_window():
    item = {"role": "dam", "sire": "Storm Cat", "yob_range": (2000, 2012)}
    rows = [
        {"id": "1", "sire": "Seattle Slew", "foal_year": "2005", "status": "ok"},
        {"id": "2", "sire": "STORM CAT", "foal_year": "2006", "status": "pending"},
        {"id": "3", "sire": "Storm Cat", "foal_year": "1988", "status": "ok"},
    ]
    row, why = sp.pick_row(rows, item)
    assert row["id"] == "2" and why == ""


def test_pick_row_prefers_single_ok_and_flags_ambiguous():
    item = {"role": "sire", "sire": "", "yob_range": None}
    rows = [{"id": "1", "status": "pending"}, {"id": "2", "status": "ok"}]
    assert sp.pick_row(rows, item)[0]["id"] == "2"
    rows = [{"id": "1", "status": "ok"}, {"id": "2", "status": "ok"}]
    assert sp.pick_row(rows, item) == (None, "ambiguous rows")
    assert sp.pick_row([], item) == (None, "no row")


def test_new_row_key_avoids_taken_keys():
    item = {"role": "dam", "name_key": "BELLA", "sire": "Tapit"}
    assert sp.new_row_key(item, lambda key: False) == "BELLA"
    assert sp.new_row_key(item, lambda key: True) == "BELLA [dam by TAPIT]"


def test_due_respects_done_and_retry_days():
    now = datetime.now(timezone.utc)
    item = {"key": "dam:X:"}
    assert sp.due(item, {}, now.timestamp())
    states = {"dam:X:": {"status": "complete", "last_attempt": now - timedelta(days=400)}}
    assert not sp.due(item, states, now.timestamp())
    states = {"dam:X:": {"status": "incomplete", "last_attempt": now - timedelta(days=5)}}
    assert not sp.due(item, states, now.timestamp())
    states = {"dam:X:": {"status": "incomplete", "last_attempt": now - timedelta(days=31)}}
    assert sp.due(item, states, now.timestamp())


def test_yearless_search_narrows_to_thoroughbred_stallion():
    html = (FIXTURES / "search_storm_cat.html").read_text()
    assert resolve_html(html, "")["kind"] == "ambiguous"
    resolved = resolve_html(html, "", None, None, (1975, 1990), "sire")
    assert resolved["kind"] == "candidate"
    assert resolved["candidate"]["name"] == "Storm Cat"
    assert resolved["candidate"]["yob"] == "1983"


def test_narrow_yearless_keeps_hits_when_a_filter_empties_them():
    rows = [{"breed": "QH", "sex": "Mare", "yob": "1957"}]
    assert narrow_yearless(rows, (2000, 2010), "sire") == rows


def test_pick_row_merges_duplicate_queue_rows():
    item = {"role": "dam", "sire": "Holy Bull", "yob_range": None}
    rows = [
        {"id": "1", "sire": "Holy Bull", "foal_year": "1997", "status": "pending"},
        {"id": "2", "sire": "Holy Bull", "foal_year": None, "status": "pending"},
    ]
    assert sp.pick_row(rows, item)[0]["id"] == "1"


def test_breeding_stallion_name_drops_southern_count_only():
    from crossr_pipeline.breeding_import import stallion_name

    assert stallion_name("Gun Runner (6)") == "Gun Runner"
    assert stallion_name("Candy Ride (ARG)") == "Candy Ride (ARG)"


def test_backfill_maps_equibase_values():
    from crossr_pipeline.sales_backfill import is_named, map_color, map_place

    assert map_color("DK B/BR") == "DB/BR" and map_color("Gr/ro") == "GR/RO"
    assert map_place("KY") == "KENTUCKY" and map_place("IRE") == "IRE"
    assert is_named("Adventurous Lady")
    assert not is_named("Hip 0002") and not is_named("TAPIT x ZAGORA '24") and not is_named("2025-QUARIA DREAM")


def test_catalog_hip_horses_and_order():
    from crossr_pipeline import catalog_priority as cp

    broodmare = {"HIP": "0004", "NAME": "American Caviar", "SEX": "M", "SIRE": "Curlin", "DAM": "Caviar",
                 "SIRE OF DAM": "Tapit", "YEAR OF BIRTH": "01/16/2019", "COVERING SIRE": "Nyquist",
                 "SESSION": "1", "BOOK": "1"}
    parts = {i["part"]: i for i in cp.hip_horses(broodmare)}
    assert set(parts) == {"sire", "dam", "cover", "horse"}
    assert parts["dam"]["yob_range"] == (1994, 2016) and parts["dam"]["sire"] == "Tapit"
    assert parts["horse"]["role"] == "dam" and parts["horse"]["yob_range"] == (2019, 2019)
    weanling = {"HIP": "0001", "NAME": "", "SEX": "C", "SIRE": "Life Is Good", "DAM": "Alexa Lou",
                "SESSION": "2", "BOOK": "1", "YEAR OF BIRTH": "02/13/2026"}
    assert {i["part"] for i in cp.hip_horses(weanling)} == {"sire", "dam"}
    assert cp.sort_key(broodmare) < cp.sort_key(weanling)
    assert cp.row_hash(weanling) != cp.row_hash({**weanling, "DAM": "Other"})
    assert cp.row_hash(weanling) == cp.row_hash({**weanling, "BARN": "9"})


def test_keeneland_merge_fills_blanks_only():
    from crossr_pipeline import keeneland

    export = {"1": {"Hip Number": "0001", "Session": "2", "Book": "1", "Color": "Dark Bay/Brown",
                    "Dam Sire": "Speightstown", "DOB": "02/13/2026", "State Foaled": "KY  ",
                    "Cover": "", "Pregnant": "", "Sold As": "Weanling"}}
    cols, rows, filled = keeneland.merge_rows(["SESSION", "HIP", "COLOR"], [{"HIP": "0001", "COLOR": "B"}], export)
    assert cols[:2] == ["SESSION", "BOOK"]
    assert rows[0]["COLOR"] == "B" and rows[0]["SESSION"] == "2" and rows[0]["FOALED"] == "KY"
    assert rows[0]["SIRE OF DAM"] == "Speightstown" and filled["COLOR"] == 0


def test_pick_row_prefers_rows_that_name_the_sire():
    item = {"role": "dam", "sire": "A.P. Indy", "yob_range": None}
    rows = [{"id": "1", "sire": None, "status": "pending"}, {"id": "2", "sire": "A. P. Indy", "status": "pending"}]
    assert sp.pick_row(rows, item)[0]["id"] == "2"


def test_catalog_skips_young_named_horses():
    from crossr_pipeline import catalog_priority as cp

    yearling = {"SALE TITLE": "Eastern Fall Yearlings (2026)", "HIP": "3", "NAME": "Prince Leone", "SEX": "C",
                "SIRE": "Tacitus", "DAM": "Leona", "YEAR OF BIRTH": "04/01/2025"}
    assert {i["part"] for i in cp.hip_horses(yearling)} == {"sire", "dam"}

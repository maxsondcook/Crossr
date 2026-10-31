"""One race_horses row per Equibase refno: a queue row for a stored horse merges into it.

Runs on the pipeline's SQLite stage (crossr_pipeline.stage), which implements
the same db API as pgdb, so no database is needed.
"""

import pytest

from crossr_pipeline import sales_parents, stage
from equibase_scraper import run


@pytest.fixture
def conn(tmp_path, monkeypatch):
    conn = stage.connect(tmp_path / "stage.sqlite")
    stage.meta_set(conn, "id_next", 100)
    stage.meta_set(conn, "id_end", 199)
    monkeypatch.setattr(run, "db", stage)
    return conn


def _profile(refno="10040120", starts=2):
    return {
        "display_name": "Call Paul", "foal_year": "2016", "sire": "Friesan Fire", "dam": "Avani",
        "sex": "C", "equibase_refno": refno, "registry": "T",
        "profile_url": f"https://www.equibase.com/profiles/Results.cfm?type=Horse&refno={refno}&registry=T",
        "year_stats": [{"year": "2018", "starts": str(starts)}],
        "starts": [{"race_date": f"2018-0{i + 1}-01", "track": "SAR", "place": "1"} for i in range(starts)],
    }


def _queue(conn, key, year="2016", sire="", dam=""):
    stage.insert_batch_horse(conn, {"pedigree_key": key, "name_key": "CALL PAUL", "foal_year": year,
                                    "display_name": "Call Paul", "sire": sire, "dam": dam,
                                    "queue_batch": "catalog-2026-10-15"})
    return stage.find_horses(conn, key, "CALL PAUL", None)[0]["id"]


def test_second_queue_row_for_a_stored_horse_merges_into_it(conn):
    first = _queue(conn, "CALL PAUL (2016)")
    second = _queue(conn, "CALL PAUL | FRIESAN FIRE | AVANI", sire="Friesan Fire", dam="Avani")
    assert run._store_resolved(conn, first, {"kind": "profile", "profile": _profile(starts=2)}) == "ok starts=2"

    summary = run._store_resolved(conn, second, {"kind": "profile", "profile": _profile(starts=3)})

    assert summary == f"ok starts=3 merged into {first}"
    kept, merged = stage.get_by_id(conn, first), stage.get_by_id(conn, second)
    assert kept["status"] == "ok" and kept["equibase_refno"] == "10040120"
    assert len(stage.start_rows(conn, first)) == 3  # the newer record replaced the kept one
    assert merged["status"] == run.MERGED and merged["detail"] == f"{run.MERGED_PREFIX}{first}"
    assert merged["equibase_refno"] is None and merged["sire"] is None
    assert merged["pedigree_key"] == "CALL PAUL | FRIESAN FIRE | AVANI"  # still taken, not queued again
    assert stage.start_rows(conn, second) == [] and stage.year_rows(conn, second) == []
    assert stage.find_by_equibase_refno(conn, "10040120")["id"] == first
    assert run.follow_merged(conn, merged)["id"] == first
    assert not stage.insert_batch_horse(conn, {"pedigree_key": "CALL PAUL | FRIESAN FIRE | AVANI",
                                               "name_key": "CALL PAUL"})
    assert second not in {r["id"] for r in stage.resume_horses(conn)}


def test_refresh_of_the_stored_row_and_new_horses_are_saved_in_place(conn):
    first = _queue(conn, "CALL PAUL (2016)")
    other = _queue(conn, "STAGE MAGIC (2007)", year="2007")
    run._store_resolved(conn, first, {"kind": "profile", "profile": _profile()})
    assert run._store_resolved(conn, first, {"kind": "profile", "profile": _profile(starts=4)}) == "ok starts=4"
    assert run._store_resolved(conn, other, {"kind": "profile", "profile": _profile(refno="555")}) == "ok starts=2"
    assert stage.get_by_id(conn, other)["status"] == "ok"
    # A profile without a refno never merges.
    third = _queue(conn, "CALL PAUL | X | Y")
    assert run._store_resolved(conn, third, {"kind": "profile", "profile": _profile(refno="")}) == "ok starts=2"


def test_follow_merged_leaves_other_rows_alone(conn):
    first = _queue(conn, "CALL PAUL (2016)")
    row = stage.get_by_id(conn, first)
    assert run.follow_merged(conn, row) is row
    assert run.merged_into(row) is None
    assert run.follow_merged(conn, None) is None


def test_sale_parent_lookup_picks_the_kept_row(conn):
    first = _queue(conn, "CALL PAUL (2016)")
    second = _queue(conn, "CALL PAUL [sire by FRIESAN FIRE]")
    run._store_resolved(conn, first, {"kind": "profile", "profile": _profile()})
    run._store_resolved(conn, second, {"kind": "profile", "profile": _profile()})
    rows = stage.find_horses(conn, "CALL PAUL", "CALL PAUL", None)
    row, why = sales_parents.pick_row(rows, {"role": "sire", "sire": "", "yob_range": None})
    assert why == "" and row["id"] == first

from crossr_pipeline import stage


def _local(tmp_path):
    conn = stage.connect(tmp_path / "stage.sqlite")
    stage.meta_set(conn, "id_next", 1000)
    stage.meta_set(conn, "id_end", 1002)
    return conn


def test_new_rows_take_reserved_ids_and_are_dirty(tmp_path):
    conn = _local(tmp_path)
    assert stage.insert_batch_horse(conn, {"pedigree_key": "ZENYATTA", "name_key": "ZENYATTA",
                                           "display_name": "Zenyatta", "queue_batch": "sales-parents"})
    assert not stage.insert_batch_horse(conn, {"pedigree_key": "ZENYATTA", "name_key": "ZENYATTA"})
    stage.upsert_pending(conn, {"pedigree_key": "TAPIT (2001)", "name_key": "TAPIT", "foal_year": "2001",
                                "display_name": "Tapit"})
    rows = stage.find_horses(conn, "TAPIT", "TAPIT", "2001")
    assert [r["id"] for r in rows] == ["1001"]
    assert stage.key_taken(conn, "ZENYATTA")
    assert stage.pending(conn)["race_horses"] == 2
    stage.insert_batch_horse(conn, {"pedigree_key": "CURLIN", "name_key": "CURLIN"})
    try:
        stage.insert_batch_horse(conn, {"pedigree_key": "JUSTIFY", "name_key": "JUSTIFY"})
    except RuntimeError as exc:
        assert "reserved" in str(exc)
    else:
        raise AssertionError("ran past the reserved id block")


def test_save_profile_stages_children_and_replaces_them(tmp_path):
    conn = _local(tmp_path)
    stage.insert_batch_horse(conn, {"pedigree_key": "FLIGHTLINE", "name_key": "FLIGHTLINE"})
    profile = {"display_name": "Flightline", "foal_year": "2018", "sire": "Tapit", "sex": "H",
               "year_stats": [{"year": "2021", "starts": "2"}, {"year": "2022", "starts": "4"}],
               "starts": [{"race_date": "2022-11-05", "track": "KEE", "place": "1"}]}
    stage.save_profile(conn, "1000", profile, "ok", "", "2026-10-30T00:00:00")
    stage.save_profile(conn, "1000", {**profile, "year_stats": profile["year_stats"][:1]}, "ok", "", "x")
    row = stage.get_by_id(conn, "1000")
    assert row["status"] == "ok" and row["sire"] == "Tapit" and row["foal_year"] == "2018"
    assert [r["year"] for r in stage.year_rows(conn, "1000")] == ["2021"]
    assert len(stage.start_rows(conn, "1000")) == 1
    assert stage.pending(conn)["horses with new starts"] == 1


def test_queue_marks_count_attempts(tmp_path):
    conn = _local(tmp_path)
    stage.mark_item(conn, "pedigrees-sales", "dam:ZENYATTA:STREET CRY", "error", "x")
    stage.mark_item(conn, "pedigrees-sales", "dam:ZENYATTA:STREET CRY", "complete", "race_horses 1")
    states = stage.queue_states(conn, "pedigrees-sales")
    item = states["dam:ZENYATTA:STREET CRY"]
    assert item["status"] == "complete" and item["attempts"] == 2
    assert item["last_attempt"].tzinfo is not None
    row = conn.execute("SELECT _dirty FROM queue").fetchone()
    assert row["_dirty"] == 2  # both attempts go up at the next push


def test_pedigrees_round_trip_and_cache(tmp_path):
    conn = _local(tmp_path)
    tree = {"Horse": "Justify", "Sire": {"Horse": "Scat Daddy"}, "Dam": {"Horse": "Stage Magic"}}
    assert stage.upsert_pedigrees(conn, {"JUSTIFY (2015)": tree}) == 1
    assert stage.load_pedigree_map(conn)["JUSTIFY (2015)"] == tree
    assert stage.pending(conn)["pedigrees"] == 1
    calls = []
    build = lambda: calls.append(1) or [{"name": "x"}]  # noqa: E731
    assert stage.cached(conn, "k", "v1", build) == [{"name": "x"}]
    assert stage.cached(conn, "k", "v1", build) == [{"name": "x"}]
    stage.cached(conn, "k", "v2", build)
    assert len(calls) == 2

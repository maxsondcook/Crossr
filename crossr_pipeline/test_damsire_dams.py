from crossr_pipeline import damsire_dams as dd


def test_load_list_orders_by_recent_lots_and_sets_window(tmp_path):
    path = tmp_path / "dams.csv"
    path.write_text(
        "dam,first_sale_year,last_sale_year,earliest_foal_year,lots,lots_2010_plus,reason\n"
        "Old Mare,1995,2001,1994,9,0,not_in_data\n"
        "Wonder Woman,2011,2025,2008,20,20,ambiguous_namesakes\n"
    )
    items = dd.load_list(path)
    assert [it["name"] for it in items] == ["Wonder Woman", "Old Mare"]
    assert items[0]["yob_range"] == (1998, 2005)
    assert items[0]["key"] == "dam:WONDER WOMAN"


def test_keep_takes_tb_mares_in_window_with_a_sire():
    hits = [
        {"name": "WONDER WOMAN", "yob": "2003", "sex": "Mare", "sire": "Storm Cat", "breed": "TB"},
        {"name": "WONDER WOMAN", "yob": "1985", "sex": "Mare", "sire": "Alydar", "breed": "TB"},  # too old
        {"name": "WONDER WOMAN", "yob": "2004", "sex": "Gelding", "sire": "Tapit", "breed": "TB"},
        {"name": "WONDER WOMAN", "yob": "2002", "sex": "Mare", "sire": "Bob", "breed": "QH"},
        {"name": "WONDER WOMAN (GB)", "yob": "2000", "sex": "M", "sire": "=Sadler's Wells (IRE)", "breed": "TB"},
    ]
    kept = dd.keep(hits, (1998, 2005))
    assert [(c["yob"], c["sire"]) for c in kept] == [(2003, "Storm Cat"), (2000, "Sadler's Wells (IRE)")]
    assert dd.status_of(kept) == "ambiguous"
    assert dd.status_of(kept[:1]) == "found"
    assert dd.status_of([]) == "not_found"


def test_suffix():
    assert dd.suffix("Wonder Woman (GB)") == "GB"
    assert dd.suffix("Wonder Woman") == ""

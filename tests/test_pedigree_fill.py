"""Filling short pedigree branches from ancestors' own records (crossr_core.pedigree_fill)."""

import re

from crossr_core.pedigree_fill import complete, fill_gaps, same_horse


def clean(name):
    return re.sub(r"\s*\(\d{4}\)\s*$", "", name or "").upper().replace("'", "")


def H(name, sire=None, dam=None):
    node = {"Horse": name}
    if sire:
        node["Sire"] = sire
    if dam:
        node["Dam"] = dam
    return node


# Classy Act's catalog tree stops at Country Romance; Into Mischief's own tree goes deeper.
INTO_MISCHIEF = H("INTO MISCHIEF (2005)",
                  H("HARLAN'S HOLIDAY (1999)",
                    H("HARLAN (1989)", H("STORM CAT (1983)"),
                      H("COUNTRY ROMANCE (1976)", H("HALO (1969)"), H("SWEET ROMANCE (1968)")))),
                  H("LESLIE'S LADY (1996)"))
CLASSY_ACT = H("CLASSY ACT",
               H("INTO MISCHIEF (2005)",
                 H("HARLAN'S HOLIDAY (1999)", H("HARLAN (1989)", H("STORM CAT (1983)"), H("COUNTRY ROMANCE (1976)")))),
               H("ACTING CLASS (2009)"))
DB = {"INTO MISCHIEF (2005)": INTO_MISCHIEF}


def lookup(name):
    return DB.get(name, {})


def test_missing_parents_come_from_the_sires_own_record():
    out = fill_gaps(CLASSY_ACT, 5, lookup, clean)
    cr = out["Sire"]["Sire"]["Sire"]["Dam"]
    assert cr["Horse"] == "COUNTRY ROMANCE (1976)"
    assert cr["Sire"]["Horse"] == "HALO (1969)" and cr["Dam"]["Horse"] == "SWEET ROMANCE (1968)"
    assert out["Sire"]["Dam"]["Horse"] == "LESLIE'S LADY (1996)"  # whole missing branch copied


def test_existing_entries_are_never_replaced():
    tree = H("X", H("INTO MISCHIEF (2005)", H("SOMEONE ELSE (1990)")), H("D"))
    out = fill_gaps(tree, 5, lookup, clean)
    assert out["Sire"]["Sire"]["Horse"] == "SOMEONE ELSE (1990)"
    assert out["Sire"]["Dam"]["Horse"] == "LESLIE'S LADY (1996)"  # only the gap is filled


def test_namesake_with_another_year_is_not_used():
    tree = H("X", H("INTO MISCHIEF (1985)"), H("D"))
    out = fill_gaps(tree, 5, lambda n: INTO_MISCHIEF if clean(n) == "INTO MISCHIEF" else {}, clean)
    assert "Sire" not in out["Sire"]


def test_input_is_not_mutated_and_complete_trees_skip_lookups():
    calls = []
    full = H("A", H("B", H("C"), H("D")), H("E", H("F"), H("G")))
    out = fill_gaps(full, 2, lambda n: calls.append(n) or {}, clean)
    assert out == full and calls == []
    before = repr(CLASSY_ACT)
    fill_gaps(CLASSY_ACT, 5, lookup, clean)
    assert repr(CLASSY_ACT) == before


def test_helpers():
    assert same_horse("CURLIN (2004)", "Curlin", clean)
    assert not same_horse("CURLIN (2004)", "CURLIN (1990)", clean)
    assert complete(H("A", H("B"), H("C")), 1) and not complete(H("A", H("B")), 1)
    assert not complete(H("A", H("UNKNOWN"), H("C")), 1)

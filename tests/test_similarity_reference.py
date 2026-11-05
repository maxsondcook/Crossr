"""pedigree_similarity with a precomputed SimilarityReference must match the plain call exactly.

The hypomating report compares one foal against hundreds of horses; the reference
object builds the foal's ancestor map once instead of once per comparison
(nightly bug hunt 2026-11-05: hypomating report 2.1-2.5 s against a 2.0 s budget).
"""

import random
import sys

import pytest

from crossr_core import sample_db


class _EmptyDatabase:
    """Stands in for Postgres while crossr_core.horses (via main) loads its tables at import."""

    def __getattr__(self, name):
        if name == "table_version":
            return lambda *a, **k: 0.0
        return lambda *a, **k: iter(())


if "crossr_core.horses" not in sys.modules:
    _real_pg = sample_db._pg
    sample_db._pg = lambda: _EmptyDatabase()
    try:
        from crossr_core import horses
    finally:
        sample_db._pg = _real_pg
else:
    from crossr_core import horses


NAMES = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel", "India", "Juliet",
         "Kilo", "Lima", "Mike", "November", "Oscar", "Papa"]


def _random_tree(rng, depth=0, max_depth=6):
    # Names repeat, sometimes with a foaling year and sometimes without (namesakes),
    # and some nodes stop early so _parents_of falls back to main.pedigree_tree.
    name = rng.choice(NAMES)
    if rng.random() < 0.5:
        name = f"{name} ({rng.choice([1990, 1995, 2001])})"
    node = {"Horse": name}
    if depth < max_depth and rng.random() < 0.85:
        node["Sire"] = _random_tree(rng, depth + 1, max_depth)
        node["Dam"] = _random_tree(rng, depth + 1, max_depth)
    return node


@pytest.fixture
def lookup_db(monkeypatch):
    rng = random.Random(7)
    db = {}
    for base in NAMES:
        for label in (base, f"{base} (1990)", f"{base} (1995)"):
            db[label.upper()] = _random_tree(rng, 1, 4) | {"Horse": label}

    def fake_pedigree_tree(name):
        return db.get(str(name or "").strip().upper())

    monkeypatch.setattr(horses.main, "pedigree_tree", fake_pedigree_tree)
    return db


def test_reference_matches_plain_call(lookup_db):
    rng = random.Random(2026)
    for _ in range(40):
        foal = _random_tree(rng)
        ref = horses.SimilarityReference(a_tree=foal)
        for _ in range(25):
            other = _random_tree(rng)
            plain = horses.pedigree_similarity(a_tree=foal, b_tree=other)
            fast = horses.pedigree_similarity(b_tree=other, reference=ref)
            assert fast == plain
        # Named lookups (the report loops pass b by name).
        for name in list(lookup_db)[:10]:
            assert horses.pedigree_similarity(b=name, reference=ref) == horses.pedigree_similarity(a_tree=foal, b=name)


def test_reference_cache_not_mutated_between_calls(lookup_db):
    rng = random.Random(11)
    foal = _random_tree(rng)
    ref = horses.SimilarityReference(a_tree=foal)
    before = dict(ref.cache)
    for _ in range(20):
        horses.pedigree_similarity(b_tree=_random_tree(rng), reference=ref)
    assert ref.cache == before


def test_reference_without_horse_returns_none():
    ref = horses.SimilarityReference(a_tree={"Horse": "UNKNOWN"})
    assert horses.pedigree_similarity(b_tree={"Horse": "Alpha"}, reference=ref) is None

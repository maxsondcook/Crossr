"""Speed fixes for the catalog, hip, profile and hypomating screens.

These run without a database. They lock the behaviour that was making those
screens wait (copying a whole table once per lot, walking two pedigrees on
every comparison, opening a new Postgres connection per query) and record how
long the old and new paths take on this machine.
"""

import time

from psycopg.rows import tuple_row

import crossr_core.railway_db as railway_db
import crossr_core.sample_db as sample_db

# Importing the API pulls the pedigree and broodmare tables. Those reads are
# stubbed for this module only, then the real functions are put back so the
# rest of the suite still talks to Postgres when DATABASE_URL is set.
_real_load_table = sample_db.load_table
_real_sample_version = sample_db.table_version
_real_require = railway_db.require
_real_pg_version = railway_db.table_version
sample_db.load_table = lambda table, refresh=False: []
sample_db.table_version = lambda table: 0.0
railway_db.require = lambda: None
railway_db.table_version = lambda table, max_age=None: 0.0

from crossr_core import horses, stallion_rankings_rich
import hypomating_engine
import crossr_api.app as api

sample_db.load_table = _real_load_table
sample_db.table_version = _real_sample_version
railway_db.require = _real_require
railway_db.table_version = _real_pg_version


def _fee_rows(n=25000):
    return [
        {"Year": "2024", "Stallion": f"Stallion {i}", "Stud Fee": "$10,000", "Farm": "", "Source List": "", "Notes": ""}
        for i in range(n)
    ]


def test_stud_fee_history_loads_the_table_once(monkeypatch):
    """A 3,406-hip catalog used to copy the stud-fee table once per lot."""
    rows = _fee_rows()
    calls = {"n": 0}

    def load(table, refresh=False):
        calls["n"] += 1
        sample_db._MTIME[table] = 7.0
        return list(rows)  # load_table copies the cached rows on every call

    monkeypatch.setattr(sample_db, "table_version", lambda table: 7.0)
    monkeypatch.setattr(sample_db, "load_table", load)
    monkeypatch.setattr(sample_db, "_FEE_HISTORY", None)

    first = sample_db.stud_fee_history()
    started = time.perf_counter()
    again = first
    for _ in range(3405):
        again = sample_db.stud_fee_history()
    after = time.perf_counter() - started

    assert calls["n"] == 1
    assert again is first
    assert first[sample_db.name_key("Stallion 1")][2024] == 10000

    # What the catalog did before the cache check moved above load_table:
    # load_table copies the whole stud-fee list on every lot.
    started = time.perf_counter()
    for _ in range(3406):
        list(rows)
    before = time.perf_counter() - started

    print(f"\nstud-fee catalog path: before {before:.3f}s (3406 copies), after {after:.3f}s (3406 cache hits)")
    assert after < before / 5
    assert after < 0.5


def test_ranking_rows_match_the_old_query(monkeypatch):
    rows = [
        {"stallion": "Into Mischief (2005)", "year": "2024", "list": "B", "table_name": "t", "rank": "1"},
        {"stallion": "Into Mischief", "year": "2023", "list": "A", "table_name": "t", "rank": "2"},
        {"stallion": "Into Mischief (2005)", "year": "2024", "list": "A", "table_name": "t", "rank": "3"},
        {"stallion": "Other Horse", "year": "2024", "list": "A", "table_name": "t", "rank": "9"},
    ]
    monkeypatch.setattr(stallion_rankings_rich.sample_db, "table_version", lambda table: 1.0)
    monkeypatch.setattr(stallion_rankings_rich.sample_db, "load_table", lambda table, refresh=False: rows)
    monkeypatch.setattr(stallion_rankings_rich, "_RANK_INDEX", None)

    found = stallion_rankings_rich._ranking_rows("into mischief")
    assert [row["rank"] for row in found] == ["3", "1", "2"]
    exact = stallion_rankings_rich._ranking_rows("INTO MISCHIEF (2005)")
    assert [row["rank"] for row in exact] == ["3", "1"]


def test_race_horse_index_matches_name_key(monkeypatch):
    from crossr_core import identity

    rows = [
        {"name_key": "into mischief", "sex": "H", "foal_year": "2005", "sire": "Harlan's Holiday"},
        {"name_key": "INTO MISCHIEF", "sex": "F", "foal_year": "2018", "sire": "Other"},
    ]
    monkeypatch.setattr(identity.sample_db, "table_version", lambda table: 3.0)
    monkeypatch.setattr(identity.sample_db, "load_table", lambda table, refresh=False: rows)
    monkeypatch.setattr(identity, "_RACE_ROWS", None)

    facts = identity.horse_facts(
        "Into Mischief",
        {"Horse": "Into Mischief (2005)", "Sire": {"Horse": "Harlan's Holiday"}, "Dam": {"Horse": "Leslie's Lady"}},
    )
    assert facts["sex"] == "H"
    assert facts["year"] == 2005
    # Second call is the in-memory index, not another table load.
    assert identity._race_horse_rows("Into Mischief")[0][0] == "H"


def _tree(name, year, sire=None, dam=None):
    node = {"Horse": f"{name} ({year})"}
    if sire is not None:
        node["Sire"] = sire
    if dam is not None:
        node["Dam"] = dam
    return node


def _line(prefix, year, depth):
    if depth <= 0:
        return _tree(prefix, year)
    return _tree(prefix, year, _line(prefix + "s", year - 8, depth - 1), _line(prefix + "d", year - 8, depth - 1))


def test_prepared_similarity_matches_the_walk():
    shared = _line("Shared Sire", 2004, 4)
    dam_a = _line("Dam A", 2006, 3)
    dam_b = _line("Dam B", 2007, 3)
    sister_sire = _line("Sister Sire", 1998, 2)
    sister_dam = _line("Sister Dam", 1999, 2)
    cases = {
        "same horse": (
            _tree("Alpha", 2024, shared, dam_a),
            _tree("Alpha", 2024, shared, dam_a),
            "Same horse",
        ),
        "full siblings": (
            _tree("Alpha", 2024, shared, dam_a),
            _tree("Beta", 2023, shared, dam_a),
            "Full siblings",
        ),
        "same sire": (
            _tree("Alpha", 2024, shared, dam_a),
            _tree("Beta", 2023, shared, dam_b),
            "Same sire",
        ),
        "3/4 siblings": (
            _tree("Alpha", 2024, shared, _tree("Dam One", 2008, sister_sire, sister_dam)),
            _tree("Beta", 2023, shared, _tree("Dam Two", 2009, sister_sire, sister_dam)),
            "3/4 siblings",
        ),
        "unrelated": (
            _line("Left", 2022, 3),
            _line("Right", 2021, 3),
            None,
        ),
    }
    for label, (a, b, expect) in cases.items():
        walked = horses.pedigree_similarity(a_tree=a, b_tree=b)
        prepared = horses._similarity_prepared(horses._prepare(a), horses._prepare(b), b_name="b")
        assert prepared["percent"] == walked["percent"], label
        assert prepared["label"] == walked["label"] == expect, label

    foals = [
        _tree(f"Foal {i}", 2024, shared, _line(f"Dam {i}", 2006, 3))
        for i in range(40)
    ]
    ref = foals[0]
    started = time.perf_counter()
    for other in foals:
        horses.pedigree_similarity(a_tree=ref, b_tree=other)
    before = time.perf_counter() - started

    ref_prep = horses._prepare(ref)
    preps = [horses._prepare(other) for other in foals]
    started = time.perf_counter()
    for prep in preps:
        horses._similarity_prepared(ref_prep, prep)
    after = time.perf_counter() - started
    print(f"\nsimilarity x40: walk {before:.3f}s, prepared {after:.3f}s")
    assert after < before


def test_top_crosses_limit_zero_is_uncapped(monkeypatch):
    ranked = [{"broodmare_sire": "A"}, {"broodmare_sire": "B"}, {"broodmare_sire": "C"}]
    monkeypatch.setattr(hypomating_engine, "_crosses_by_sire", lambda pedigree_db=None: {"INTO MISCHIEF": ranked})
    capped = hypomating_engine.top_crosses_payload(None, "Into Mischief", limit=2)
    assert [row["broodmare_sire"] for row in capped["crosses"]] == ["A", "B"]
    all_rows = hypomating_engine.top_crosses_payload(None, "Into Mischief", limit=0)["crosses"]
    assert len(all_rows) == 3
    all_rows.append({"broodmare_sire": "extra"})
    assert len(ranked) == 3


class _FakeConn:
    def __init__(self):
        self.closed = False
        self.row_factory = tuple_row
        self.commits = 0

    def execute(self, sql):
        return self

    def fetchone(self):
        return (1,)

    def rollback(self):
        return None

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


def test_connection_pool_reuses_and_resets(monkeypatch):
    made = []

    def new():
        conn = _FakeConn()
        made.append(conn)
        return conn

    monkeypatch.setattr(railway_db, "_new_connection", new)
    monkeypatch.setattr(railway_db, "require", lambda: None)
    monkeypatch.setattr(railway_db, "_pool_idle", [])
    monkeypatch.setattr(railway_db, "_pool_open", 0)
    monkeypatch.setattr(railway_db, "_POOL_MAX", 1)

    with railway_db.connect(row_factory="dict") as first:
        assert first.row_factory == "dict"
    assert first.row_factory is tuple_row
    assert first.commits == 1

    with railway_db.connect() as second:
        assert second is first
    assert len(made) == 1

    held = railway_db.connect()
    held_conn = held.__enter__()
    with railway_db.connect() as extra:
        assert extra is not held_conn
        overflow = extra
    assert overflow.closed
    held.__exit__(None, None, None)
    assert not held_conn.closed
    assert len(made) == 2


def test_precompute_does_not_run_during_tests(monkeypatch):
    import crossr_api.app as api

    def explode(*args, **kwargs):
        raise AssertionError("precompute should not open the database under pytest")

    monkeypatch.setattr(railway_db, "connect", explode)
    api._precompute_missing_hips()

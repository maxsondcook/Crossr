"""Rebuild crossr_dev's big tables as the e2e / identity test sample, from production.

Only crossr_dev is written. On production the script only creates TEMP tables
(the selection) and rolls back. The sample:

  * sales_lots: lots naming a test subject (tests/e2e/conftest.py,
    tests/test_identity.py) as horse, sire, dam or damsire; every 2026 lot;
    2025 lots by a 2026 sire (comparables); lots of the Saratoga 2026 hips'
    dams and their sire x damsire crosses; lots out of mares by a test mare's
    sire, and lots of graded stakes horses (by name or sire + dam), for the
    auction history of similar crosses
  * race_horses (+ seasons, starts): every horse named in those lots, and the
    subjects' offspring and daughters' foals
  * pedigrees: those horses, every graded stakes horse (stallion suggestions
    read their parents) and every stallion with a fee since 2023

Other tables (stud fees, rankings, breeding seasons, graded stakes, models,
catalogs) are left as they are. Then sales_lot_index is rebuilt, versions are
bumped and the tables are compacted.

    scripts/pipeline/railway_env.sh crossr_dev .venv/bin/python scripts/pipeline/shrink_dev.py           # counts only
    scripts/pipeline/railway_env.sh crossr_dev .venv/bin/python scripts/pipeline/shrink_dev.py --apply
"""
import os
import sys
import time
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TARGET = os.environ["DATABASE_URL"]
assert TARGET.rsplit("/", 1)[-1] == "crossr_dev", "writes crossr_dev only"
SOURCE = TARGET.rsplit("/", 1)[0] + "/railway"
APPLY = "--apply" in sys.argv

SUBJECTS = [
    "AMERICAN PHAROAH", "INTO MISCHIEF", "NOT THIS TIME", "JUSTIFY", "CURLIN", "ESSENTIAL QUALITY", "TAPIT",
    "FLIGHTLINE", "SIERRA LEONE", "FIERCENESS", "CONSTITUTION", "LITTLE BIG BEAR", "MCCRAKEN", "ENGLISHMAN",
    "ZENYATTA", "ACCELERATE", "VIRGINIA KEY", "SIPPICAN HARBOR", "OFF TOPIC", "CROWNED", "STAGE MAGIC",
]
SARATOGA = "Fasig-Tipton_The_Saratoga_Sale(2026).csv"


def name(col: str) -> str:
    """Upper-case name without "(2015)", "(KY) 124" and the like."""
    return f"upper(btrim(regexp_replace({col}, '\\s*\\(.*$', '')))"


TREE_SIRE, TREE_DAM, GS_HORSE = "p.tree->'Sire'->>'Horse'", "p.tree->'Dam'->>'Horse'", '"Horse Name"'
STEPS = [
    "CREATE TEMP TABLE subjects AS SELECT unnest(%(s)s::text[]) AS n",
    "CREATE TEMP TABLE sar AS SELECT * FROM sales_lots WHERE source_file = %(sar)s",
    "CREATE TEMP TABLE s_cross AS SELECT DISTINCT upper(sire) AS sire, upper(damsire) AS damsire FROM sar",
    "CREATE TEMP TABLE sires26 AS SELECT DISTINCT upper(sire) AS n FROM sales_lots WHERE catalog_year = '2026'",
    # graded stakes horses and their parents (pedigrees), for auction history of similar crosses
    f"CREATE TEMP TABLE gsw AS SELECT DISTINCT {name('p.key')} AS n, {name(TREE_SIRE)} AS sire, "
    f"{name(TREE_DAM)} AS dam FROM pedigrees p WHERE {name('p.key')} IN (SELECT {name(GS_HORSE)} FROM graded_stakes)",
    "CREATE TEMP TABLE k_lots AS SELECT * FROM sales_lots s WHERE catalog_year = '2026' "
    "OR upper(s.name) IN (SELECT n FROM gsw) OR (upper(s.sire), upper(s.dam)) IN (SELECT sire, dam FROM gsw) "
    "OR (catalog_year = '2025' AND upper(s.sire) IN (SELECT n FROM sires26)) "
    "OR upper(s.sire) IN (SELECT n FROM subjects) OR upper(s.dam) IN (SELECT n FROM subjects) "
    "OR upper(s.damsire) IN (SELECT n FROM subjects) OR upper(s.name) IN (SELECT n FROM subjects) "
    "OR upper(s.dam) IN (SELECT upper(dam) FROM sar) "
    "OR upper(s.damsire) IN (SELECT upper(damsire) FROM sales_lots WHERE upper(dam) IN (SELECT n FROM subjects)) "
    "OR (upper(s.sire), upper(s.damsire)) IN (SELECT sire, damsire FROM s_cross)",
    "CREATE TEMP TABLE lot_names AS SELECT n FROM subjects UNION "
    "SELECT upper(x) FROM k_lots, LATERAL (VALUES (sire), (dam), (damsire), (name)) v(x) WHERE COALESCE(x, '') <> ''",
    f"CREATE TEMP TABLE k_horses AS SELECT * FROM race_horses h WHERE {name('h.display_name')} IN (SELECT n FROM lot_names) "
    f"OR {name('h.pedigree_key')} IN (SELECT n FROM lot_names) "
    "OR upper(h.sire) IN (SELECT n FROM subjects) OR upper(h.dam) IN (SELECT n FROM subjects) "
    "OR upper(h.damsire) IN (SELECT n FROM subjects)",
    "CREATE TEMP TABLE k_seasons AS SELECT * FROM race_seasons WHERE horse_id IN (SELECT id FROM k_horses)",
    "CREATE TEMP TABLE k_starts AS SELECT * FROM race_starts WHERE horse_id IN (SELECT id FROM k_horses)",
    f"CREATE TEMP TABLE ped_names AS SELECT n FROM lot_names UNION SELECT {name('display_name')} FROM k_horses "
    f"UNION SELECT {name('\"Horse Name\"')} FROM graded_stakes "
    f"UNION SELECT {name('\"Stallion\"')} FROM stud_fees WHERE \"Year\" >= '2023'",
    f"CREATE TEMP TABLE k_peds AS SELECT * FROM pedigrees WHERE {name('key')} IN (SELECT n FROM ped_names)",
]
TABLES = [("sales_lots", "k_lots"), ("race_horses", "k_horses"), ("race_seasons", "k_seasons"),
          ("race_starts", "k_starts"), ("pedigrees", "k_peds")]
COMPACT = ["sales_lot_index", "sales_catalogs", "stallion_rankings", "breeding_seasons", "graded_stakes",
           "upcoming_hip_cache", "stud_fees"]

src = psycopg.connect(SOURCE)
dst = psycopg.connect(TARGET)
assert dst.execute("SELECT current_database()").fetchone()[0] == "crossr_dev"
before = dst.execute("SELECT pg_size_pretty(pg_database_size('crossr_dev'))").fetchone()[0]
started = time.monotonic()
for sql in STEPS:
    src.execute(sql, {"s": SUBJECTS, "sar": SARATOGA})
for table, keep in TABLES:
    total = src.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    kept = src.execute(f"SELECT count(*) FROM {keep}").fetchone()[0]
    print(f"{table:<14} keep {kept:>7} of {total:>7} (production)", flush=True)
if not APPLY:
    print(f"dry run ({time.monotonic() - started:.0f}s); crossr_dev is {before}")
    sys.exit(0)

from crossr_core import railway_db  # noqa: E402

for table, keep in TABLES:
    cols = [r[0] for r in src.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s AND table_schema = 'public' "
        "ORDER BY ordinal_position", (table,))]
    col_sql = ", ".join(f'"{c}"' for c in cols)
    dst.execute(f"TRUNCATE {table}")
    with src.cursor() as out, dst.cursor() as into:
        with out.copy(f"COPY (SELECT {col_sql} FROM {keep}) TO STDOUT") as reader, \
                into.copy(f"COPY {table} ({col_sql}) FROM STDIN") as writer:
            for block in reader:
                writer.write(block)
    n = dst.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    version = railway_db._bump(dst, table, n)
    if table == "sales_lots":
        railway_db._rebuild_sales_index(dst, version)
    print(f"{table:<14} {n} rows in crossr_dev", flush=True)
for seq, table in (("crossr_race_horses_id_seq", "race_horses"), ("crossr_race_seasons_id_seq", "race_seasons"),
                   ("crossr_race_starts_id_seq", "race_starts")):
    dst.execute(f"SELECT setval('{seq}', GREATEST((SELECT last_value FROM {seq}), "
                f"(SELECT COALESCE(MAX(id::bigint), 1) FROM {table} WHERE id ~ '^[0-9]+$')))")
for b in [r[0] for r in dst.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                                     "AND tablename LIKE '%%backup%%'")]:
    dst.execute(f'DROP TABLE "{b}"')
dst.commit()
src.rollback()
dst.autocommit = True
for table in [t for t, _ in TABLES] + COMPACT:  # FULL gives the space back
    dst.execute(f"VACUUM FULL ANALYZE {table}")
after = dst.execute("SELECT pg_size_pretty(pg_database_size('crossr_dev'))").fetchone()[0]
print(f"crossr_dev {before} -> {after} ({time.monotonic() - started:.0f}s)")

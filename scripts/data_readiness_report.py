"""Data completeness and model-readiness report (master prompt Phases 4.6 and 14.5).

Read-only: runs aggregate SQL against DATABASE_URL and writes
docs/data-readiness.md (and prints it). Nothing is modified.

Usage:
    python3 scripts/data_readiness_report.py [--out docs/data-readiness.md]

Definitions used for sale lots (sales_lot_index joined to sales_catalogs):
  * eligible: yearling or weanling lot (age at sale 0-1 from birth_year), not out
  * verified price: price_num > 0 and not RNA
  * sire stud fee feature: a stud_fees row for the sire in the conception
    season (sale year - 2 for yearlings, - 1 for weanlings) with a numeric fee
  * dam race record: the dam has a race_horses row (any status)
  * dam production: the dam is recorded as the dam of a horse in race_horses or a pedigree tree
  * broodmare sire fee: a stud_fees row with a numeric fee for the damsire in
    any season up to the sale year
Name matching is on normalised names (upper, no punctuation/country suffix);
see crossr_core/identity.py for why that overcounts namesakes slightly.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crossr_core import railway_db  # noqa: E402

NORM = "upper(regexp_replace(regexp_replace(coalesce({x},''), '\\(.*?\\)', '', 'g'), '[^A-Za-z0-9 ]', '', 'g'))"


def n(x):
    return NORM.format(x=x)


SQL = {
    "horses": """
        SELECT count(*) AS race_horses,
               count(*) FILTER (WHERE foal_year ~ '^[0-9]{4}$') AS with_foal_year,
               count(*) FILTER (WHERE coalesce(sex,'') <> '') AS with_sex,
               count(*) FILTER (WHERE coalesce(equibase_refno,'') <> '') AS with_refno,
               count(*) FILTER (WHERE status = 'merged') AS merged_rows
        FROM race_horses""",
    "dup_refno": """
        SELECT count(*) FROM (SELECT equibase_refno FROM race_horses
          WHERE coalesce(equibase_refno,'') <> '' AND coalesce(status,'') <> 'merged'
          GROUP BY 1 HAVING count(*) > 1) x""",
    "dup_name_year": """
        SELECT count(*) FROM (SELECT name_key, foal_year FROM race_horses
          WHERE foal_year ~ '^[0-9]{4}$' AND coalesce(status,'') <> 'merged'
          GROUP BY 1,2 HAVING count(*) > 1) x""",
    "pedigrees": """
        SELECT count(*) AS trees,
               count(*) FILTER (WHERE tree #> '{Sire,Sire,Sire,Sire}' IS NOT NULL
                                  AND tree #> '{Dam,Dam,Dam,Dam}' IS NOT NULL) AS four_gen_tails,
               count(*) FILTER (WHERE tree #> '{Sire}' IS NOT NULL AND tree #> '{Dam}' IS NOT NULL) AS both_parents
        FROM pedigrees""",
    "stud_fees": """
        SELECT count(*) AS rows, count(DISTINCT upper("Stallion")) AS stallions,
               count(*) FILTER (WHERE "Stud Fee" ~ '[0-9]') AS numeric_fee,
               min("Year") AS first_year, max("Year") AS last_year
        FROM stud_fees""",
    "sales_overall": """
        SELECT count(*) AS lots, count(DISTINCT l.catalog_id) AS sales,
               count(DISTINCT (c.year, c.title, l.hip)) AS unique_transactions,
               count(DISTINCT l.sire_key) AS sires, count(DISTINCT l.dam_key) AS dams,
               count(DISTINCT l.damsire_key) AS broodmare_sires
        FROM sales_lot_index l JOIN sales_catalogs c ON c.id = l.catalog_id""",
}

# Normalise names once into indexed temp tables, then join (a per-row regex in
# correlated subqueries ran for 10+ minutes on production).
PREP = [
    f"""CREATE TEMP TABLE r_fees AS SELECT DISTINCT {n('"Stallion"')} AS k, "Year"::int AS y FROM stud_fees
        WHERE "Stud Fee" ~ '[0-9]' AND "Year" ~ '^[0-9]{{4}}$'""",
    "CREATE INDEX ON r_fees (k, y)",
    f"CREATE TEMP TABLE r_racers AS SELECT DISTINCT {n('display_name')} AS k FROM race_horses",
    "CREATE INDEX ON r_racers (k)",
    # A mare's produce: dams recorded on race_horses (326k horses) plus pedigree trees.
    f"""CREATE TEMP TABLE r_dams AS
        SELECT {n('dam')} AS k FROM race_horses WHERE coalesce(dam, '') <> ''
        UNION
        SELECT {n("regexp_replace(tree #>> '{{Dam,Horse}}', ' \\(\\d{{4}}\\)$', '')")} FROM pedigrees""",
    "CREATE INDEX ON r_dams (k)",
    f"""CREATE TEMP TABLE r_elig AS
        SELECT c.year AS sale_year,
               CASE WHEN c.year - substring(l.birth_year from '^[0-9]{{4}}')::int = 0 THEN 'weanling' ELSE 'yearling' END AS category,
               CASE WHEN c.year - substring(l.birth_year from '^[0-9]{{4}}')::int = 0 THEN c.year - 1 ELSE c.year - 2 END AS conception,
               (l.price_num > 0 AND coalesce(l.is_rna, 0) = 0) AS priced,
               coalesce(l.sire_key, '') <> '' AS has_sire, coalesce(l.dam_key, '') <> '' AS has_dam,
               coalesce(l.damsire_key, '') <> '' AS has_bms,
               {n('l.sire')} AS sire_k, {n('l.dam')} AS dam_k, {n('l.damsire')} AS bms_k
        FROM sales_lot_index l JOIN sales_catalogs c ON c.id = l.catalog_id
        WHERE coalesce(l.is_out, 0) = 0 AND l.birth_year ~ '^[0-9]{{4}}'
          AND c.year - substring(l.birth_year from '^[0-9]{{4}}')::int IN (0, 1)""",
]

ELIGIBLE = """
    SELECT {group} AS grp,
      count(*) AS eligible,
      round(100.0 * count(*) FILTER (WHERE priced) / count(*), 1) AS pct_verified_price,
      round(100.0 * count(*) FILTER (WHERE has_sire) / count(*), 1) AS pct_sire,
      round(100.0 * count(*) FILTER (WHERE has_dam) / count(*), 1) AS pct_dam,
      round(100.0 * count(*) FILTER (WHERE has_bms) / count(*), 1) AS pct_broodmare_sire,
      round(100.0 * count(*) FILTER (WHERE EXISTS (SELECT 1 FROM r_fees f WHERE f.k = e.sire_k AND f.y = e.conception)) / count(*), 1) AS pct_sire_fee_at_conception,
      round(100.0 * count(*) FILTER (WHERE EXISTS (SELECT 1 FROM r_fees f WHERE f.k = e.bms_k AND f.y <= e.sale_year)) / count(*), 1) AS pct_broodmare_sire_fee,
      round(100.0 * count(*) FILTER (WHERE EXISTS (SELECT 1 FROM r_dams d WHERE d.k = e.dam_k)) / count(*), 1) AS pct_dam_production,
      round(100.0 * count(*) FILTER (WHERE EXISTS (SELECT 1 FROM r_racers r WHERE r.k = e.dam_k)) / count(*), 1) AS pct_dam_race_record
    FROM r_elig e
    GROUP BY 1 ORDER BY 1
"""


def table(rows, headers):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        out.append("| " + " | ".join("" if v is None else (f"{v:,}" if isinstance(v, int) else str(v)) for v in r) + " |")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "docs" / "data-readiness.md"))
    args = ap.parse_args()
    md = [f"# Data readiness report\n\nGenerated {datetime.date.today().isoformat()} from the production database "
          "(read-only). Definitions are in `scripts/data_readiness_report.py`.\n"]
    with railway_db.connect() as conn:
        def one(key):
            cur = conn.execute(SQL[key])
            return [d.name for d in cur.description], cur.fetchone()

        cols, h = one("horses")
        dup_ref = conn.execute(SQL["dup_refno"]).fetchone()[0]
        dup_ny = conn.execute(SQL["dup_name_year"]).fetchone()[0]
        md.append("## Horses (race_horses)\n")
        md.append(table([list(h) + [dup_ref, dup_ny]], cols + ["dup_equibase_refnos", "dup_name_year_pairs"]))
        for key, title in (("pedigrees", "Pedigrees"), ("stud_fees", "Stud fees"), ("sales_overall", "Sales")):
            cols, row = one(key)
            md.append(f"\n## {title}\n")
            md.append(table([row], cols))
        conn.execute("SET statement_timeout = '300s'")
        for stmt in PREP:
            conn.execute(stmt)
        for label, group in (("Eligible yearling/weanling lots by category", "category"),
                             ("Eligible yearling/weanling lots by sale year", "sale_year::text")):
            cur = conn.execute(ELIGIBLE.replace("{group}", group))
            md.append(f"\n## {label}\n")
            md.append(table(cur.fetchall(), [d.name for d in cur.description]))
    md.append("\n## Readiness criteria (proposed)\n\n"
              "Final sale-price model training should wait until, for eligible lots in the training years:\n"
              "- verified price >= 60% (RNAs/unsold are excluded by definition, not missing data)\n"
              "- sire, dam and broodmare sire >= 98%\n"
              "- sire stud fee at conception >= 85%\n"
              "- dam production history >= 70% and dam race record >= 60%\n"
              "- duplicate Equibase refnos = 0\n")
    text = "\n".join(md) + "\n"
    Path(args.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()

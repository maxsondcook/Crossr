# Data readiness report

Generated 2026-10-31 from the production database (read-only). Definitions are in `scripts/data_readiness_report.py`.

## Horses (race_horses)

| race_horses | with_foal_year | with_sex | with_refno | merged_rows | dup_equibase_refnos | dup_name_year_pairs |
|---|---|---|---|---|---|---|
| 326,481 | 137,422 | 253,408 | 72,247 | 0 | 877 | 3,553 |

## Pedigrees

| trees | four_gen_tails | both_parents |
|---|---|---|
| 76,741 | 48,449 | 72,865 |

## Stud fees

| rows | stallions | numeric_fee | first_year | last_year |
|---|---|---|---|---|
| 25,264 | 5,735 | 19,461 | 1995 | 2027 |

## Sales

| lots | sales | unique_transactions | sires | dams | broodmare_sires |
|---|---|---|---|---|---|
| 410,669 | 421 | 401,521 | 5,180 | 82,477 | 5,215 |

## Eligible yearling/weanling lots by category

| grp | eligible | pct_verified_price | pct_sire | pct_dam | pct_broodmare_sire | pct_sire_fee_at_conception | pct_broodmare_sire_fee | pct_dam_production | pct_dam_race_record |
|---|---|---|---|---|---|---|---|---|---|
| weanling | 36,237 | 72.7 | 100.0 | 100.0 | 83.1 | 89.5 | 69.4 | 76.9 | 91.6 |
| yearling | 198,575 | 74.1 | 100.0 | 100.0 | 85.6 | 85.2 | 69.1 | 79.9 | 93.1 |

## Eligible yearling/weanling lots by sale year

| grp | eligible | pct_verified_price | pct_sire | pct_dam | pct_broodmare_sire | pct_sire_fee_at_conception | pct_broodmare_sire_fee | pct_dam_production | pct_dam_race_record |
|---|---|---|---|---|---|---|---|---|---|
| 1999 | 6,036 | 78.2 | 100.0 | 100.0 | 63.9 | 28.4 | 18.9 | 73.6 | 76.9 |
| 2000 | 7,302 | 74.6 | 100.0 | 100.0 | 65.4 | 80.8 | 21.8 | 74.3 | 77.8 |
| 2001 | 6,829 | 70.2 | 100.0 | 100.0 | 67.6 | 82.4 | 28.0 | 75.7 | 79.0 |
| 2002 | 5,698 | 76.0 | 100.0 | 100.0 | 72.6 | 84.8 | 35.1 | 80.1 | 84.0 |
| 2003 | 5,651 | 76.7 | 100.0 | 100.0 | 73.7 | 82.0 | 38.8 | 80.7 | 85.0 |
| 2004 | 11,017 | 48.1 | 100.0 | 100.0 | 85.5 | 54.0 | 27.8 | 51.8 | 92.3 |
| 2005 | 10,462 | 73.6 | 100.0 | 100.0 | 80.6 | 86.6 | 47.8 | 82.9 | 90.9 |
| 2006 | 10,373 | 73.3 | 100.0 | 100.0 | 81.2 | 85.7 | 52.9 | 81.3 | 90.5 |
| 2007 | 11,264 | 72.8 | 100.0 | 100.0 | 83.8 | 87.9 | 59.4 | 82.2 | 91.8 |
| 2008 | 10,643 | 69.1 | 100.0 | 100.0 | 84.1 | 92.5 | 63.4 | 81.0 | 91.7 |
| 2009 | 9,687 | 72.6 | 100.0 | 100.0 | 86.4 | 91.5 | 69.4 | 82.7 | 92.6 |
| 2010 | 8,948 | 72.6 | 100.0 | 100.0 | 89.3 | 89.4 | 75.2 | 81.7 | 92.3 |
| 2011 | 8,076 | 79.0 | 100.0 | 100.0 | 90.3 | 90.5 | 78.9 | 84.4 | 93.0 |
| 2012 | 6,217 | 79.4 | 100.0 | 100.0 | 92.5 | 93.1 | 83.4 | 86.8 | 94.5 |
| 2013 | 9,269 | 81.7 | 100.0 | 100.0 | 91.4 | 94.8 | 85.0 | 87.4 | 94.8 |
| 2014 | 7,589 | 76.7 | 100.0 | 100.0 | 93.0 | 92.9 | 87.4 | 85.9 | 95.0 |
| 2015 | 7,949 | 74.4 | 100.0 | 100.0 | 92.3 | 94.4 | 88.2 | 83.8 | 94.5 |
| 2016 | 8,181 | 73.7 | 100.0 | 100.0 | 90.3 | 96.0 | 87.0 | 83.6 | 97.7 |
| 2017 | 8,297 | 74.4 | 100.0 | 100.0 | 91.3 | 90.9 | 88.6 | 84.0 | 97.5 |
| 2018 | 8,548 | 76.4 | 100.0 | 100.0 | 90.5 | 90.0 | 88.4 | 82.3 | 97.3 |
| 2019 | 8,760 | 75.3 | 100.0 | 100.0 | 91.0 | 88.1 | 89.2 | 83.3 | 97.4 |
| 2020 | 7,734 | 74.8 | 100.0 | 100.0 | 91.4 | 84.8 | 89.7 | 83.0 | 97.4 |
| 2021 | 8,171 | 81.8 | 100.0 | 100.0 | 92.2 | 74.5 | 91.0 | 83.4 | 97.4 |
| 2022 | 8,458 | 81.4 | 100.0 | 100.0 | 91.3 | 91.2 | 89.8 | 81.2 | 97.4 |
| 2023 | 8,263 | 79.2 | 100.0 | 100.0 | 89.7 | 89.4 | 88.4 | 79.5 | 97.6 |
| 2024 | 8,150 | 78.7 | 100.0 | 100.0 | 86.5 | 91.7 | 85.1 | 74.0 | 97.6 |
| 2025 | 9,409 | 69.1 | 100.0 | 100.0 | 83.3 | 93.2 | 81.8 | 68.6 | 97.6 |
| 2026 | 7,831 | 68.9 | 100.0 | 100.0 | 81.3 | 91.9 | 79.3 | 72.2 | 97.7 |

## Readiness criteria (proposed)

Final sale-price model training should wait until, for eligible lots in the training years:
- verified price >= 60% (RNAs/unsold are excluded by definition, not missing data)
- sire, dam and broodmare sire >= 98%
- sire stud fee at conception >= 85%
- dam production history >= 70% and dam race record >= 60%
- duplicate Equibase refnos = 0


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
| 410,669 | 421 | 401,521 | 5,180 | 82,477 | 3,932 |

## Eligible yearling/weanling lots by category

| grp | eligible | pct_verified_price | pct_sire | pct_dam | pct_broodmare_sire | pct_sire_fee_at_conception | pct_broodmare_sire_fee | pct_dam_production | pct_dam_race_record |
|---|---|---|---|---|---|---|---|---|---|
| weanling | 36,237 | 72.7 | 100.0 | 100.0 | 69.3 | 89.5 | 61.2 | 76.9 | 91.6 |
| yearling | 198,575 | 74.1 | 100.0 | 100.0 | 72.0 | 85.2 | 61.5 | 79.9 | 93.1 |

## Eligible yearling/weanling lots by sale year

| grp | eligible | pct_verified_price | pct_sire | pct_dam | pct_broodmare_sire | pct_sire_fee_at_conception | pct_broodmare_sire_fee | pct_dam_production | pct_dam_race_record |
|---|---|---|---|---|---|---|---|---|---|
| 1999 | 6,036 | 78.2 | 100.0 | 100.0 | 31.7 | 28.4 | 9.7 | 73.6 | 76.9 |
| 2000 | 7,302 | 74.6 | 100.0 | 100.0 | 33.5 | 80.8 | 11.6 | 74.3 | 77.8 |
| 2001 | 6,829 | 70.2 | 100.0 | 100.0 | 34.6 | 82.4 | 15.0 | 75.7 | 79.0 |
| 2002 | 5,698 | 76.0 | 100.0 | 100.0 | 38.7 | 84.8 | 19.1 | 80.1 | 84.0 |
| 2003 | 5,651 | 76.7 | 100.0 | 100.0 | 40.1 | 82.0 | 22.0 | 80.7 | 85.0 |
| 2004 | 11,017 | 48.1 | 100.0 | 100.0 | 63.5 | 54.0 | 15.8 | 51.8 | 92.3 |
| 2005 | 10,462 | 73.6 | 100.0 | 100.0 | 44.9 | 86.6 | 27.6 | 82.9 | 90.9 |
| 2006 | 10,373 | 73.3 | 100.0 | 100.0 | 48.9 | 85.7 | 32.8 | 81.3 | 90.5 |
| 2007 | 11,264 | 72.8 | 100.0 | 100.0 | 53.5 | 87.9 | 39.4 | 82.2 | 91.8 |
| 2008 | 10,643 | 69.1 | 100.0 | 100.0 | 57.8 | 92.5 | 45.0 | 81.0 | 91.7 |
| 2009 | 9,687 | 72.6 | 100.0 | 100.0 | 67.5 | 91.5 | 55.4 | 82.7 | 92.6 |
| 2010 | 8,948 | 72.6 | 100.0 | 100.0 | 79.7 | 89.4 | 67.8 | 81.7 | 92.3 |
| 2011 | 8,076 | 79.0 | 100.0 | 100.0 | 83.4 | 90.5 | 73.7 | 84.4 | 93.0 |
| 2012 | 6,217 | 79.4 | 100.0 | 100.0 | 88.2 | 93.1 | 80.2 | 86.8 | 94.5 |
| 2013 | 9,269 | 81.7 | 100.0 | 100.0 | 86.9 | 94.8 | 81.3 | 87.4 | 94.8 |
| 2014 | 7,589 | 76.7 | 100.0 | 100.0 | 90.0 | 92.9 | 85.0 | 85.9 | 95.0 |
| 2015 | 7,949 | 74.4 | 100.0 | 100.0 | 89.4 | 94.4 | 85.9 | 83.8 | 94.5 |
| 2016 | 8,181 | 73.7 | 100.0 | 100.0 | 88.3 | 96.0 | 85.6 | 83.6 | 97.7 |
| 2017 | 8,297 | 74.4 | 100.0 | 100.0 | 89.9 | 90.9 | 87.8 | 84.0 | 97.5 |
| 2018 | 8,548 | 76.4 | 100.0 | 100.0 | 89.0 | 90.0 | 87.5 | 82.3 | 97.3 |
| 2019 | 8,760 | 75.3 | 100.0 | 100.0 | 89.7 | 88.1 | 88.5 | 83.3 | 97.4 |
| 2020 | 7,734 | 74.8 | 100.0 | 100.0 | 90.2 | 84.8 | 89.0 | 83.0 | 97.4 |
| 2021 | 8,171 | 81.8 | 100.0 | 100.0 | 91.0 | 74.5 | 90.1 | 83.4 | 97.4 |
| 2022 | 8,458 | 81.4 | 100.0 | 100.0 | 89.9 | 91.2 | 88.9 | 81.2 | 97.4 |
| 2023 | 8,263 | 79.2 | 100.0 | 100.0 | 88.1 | 89.4 | 87.3 | 79.5 | 97.6 |
| 2024 | 8,150 | 78.7 | 100.0 | 100.0 | 84.9 | 91.7 | 84.1 | 74.0 | 97.6 |
| 2025 | 9,409 | 69.1 | 100.0 | 100.0 | 81.3 | 93.2 | 80.5 | 68.6 | 97.6 |
| 2026 | 7,831 | 68.9 | 100.0 | 100.0 | 78.7 | 91.9 | 77.8 | 72.2 | 97.7 |

## Readiness criteria (proposed)

Final sale-price model training should wait until, for eligible lots in the training years:
- verified price >= 60% (RNAs/unsold are excluded by definition, not missing data)
- sire, dam and broodmare sire >= 98%
- sire stud fee at conception >= 85%
- dam production history >= 70% and dam race record >= 60%
- duplicate Equibase refnos = 0


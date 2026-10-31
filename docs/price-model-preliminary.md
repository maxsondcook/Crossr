# Sale-price model — PRELIMINARY run

> **Preliminary.** The data-readiness gate (docs/data-readiness.md) has not passed, so this is not the final model. It proves the pipeline end to end on the data available today. Numbers will change.

Generated 2026-10-31 by `scripts/price_model_preliminary.py`. Method: `docs/price-model.md`.

## Sources

| table | source |
|---|---|
| sales_lots | csv:/Users/maxsoncook/Desktop/Crossr/data/sales_lots.csv |
| stud_fees | postgres |
| breeding_seasons | csv:/Users/maxsoncook/Desktop/Crossr/data/breeding_seasons.csv |
| race_horses | csv:/Users/maxsoncook/Desktop/Crossr/data/race_horses.csv |
| race_seasons | csv:/Users/maxsoncook/Desktop/Crossr/data/race_seasons.csv |
| race_starts | csv:/Users/maxsoncook/Desktop/Crossr/data/race_starts.csv |
| graded_stakes | csv:/Users/maxsoncook/Desktop/Crossr/data/graded_stakes.csv |
| stallion_rankings | csv:/Users/maxsoncook/Desktop/Crossr/data/stallion_rankings.csv |
| pedigrees | postgres |

## Dataset (one row per sale transaction)

Transactions: 399,590. Eligible for the yearling/weanling model: 191,136 (172,275 sold, 18,861 RNA with a last bid).

Exclusions (each row keeps its reason):

| reason | rows |
|---|---|
| category not in the yearling/weanling model | 79,964 |
| withdrawn (out) | 71,547 |
| no price recorded | 51,703 |
| duplicate transaction (same catalog file, hip and horse) | 5,240 |

Quality flags kept in the data: catalog title vs age mismatch 194; same horse twice in one sale 270.

Feature coverage (share of eligible sales with a value):

| group | feature | coverage |
|---|---|---|
| A_sire | log_fee_conception_hist | 100.0% |
| A_sire | fee_missing | 100.0% |
| A_sire | fee_momentum | 100.0% |
| A_sire | sire_rel | 100.0% |
| A_sire | sire_log_n | 100.0% |
| A_sire | sire_log_gsw | 100.0% |
| A_sire | sire_prog_seasons | 100.0% |
| A_sire | sire_prog_earn_per_runner | 56.7% |
| A_sire | sire_prog_win_rate | 56.6% |
| A_sire | sire_prog_sw_rate | 52.4% |
| A_sire | sire_prog_gsw_rate | 39.2% |
| A_sire | log_sire_fee_conception | 85.0% |
| A_sire | log_sire_fee_initial | 92.5% |
| A_sire | log_sire_fee_highest | 92.5% |
| A_sire | log_sire_fee_latest | 92.5% |
| A_sire | sire_fee_latest_vs_initial | 92.5% |
| A_sire | sire_fee_years_listed | 92.5% |
| A_sire | sire_fee_conception_historical | 100.0% |
| B_dam_production | dam_rel | 100.0% |
| B_dam_production | dam_log_n | 100.0% |
| B_dam_production | dam_log_gsw | 100.0% |
| B_dam_production | dam_log_gsp | 100.0% |
| B_dam_production | dam_prog_ran | 100.0% |
| B_dam_production | dam_prog_won | 100.0% |
| B_dam_production | dam_prog_sw | 100.0% |
| B_dam_production | dam_prog_gsw | 100.0% |
| B_dam_production | dam_prog_g1 | 100.0% |
| B_dam_production | dam_prog_earnings | 100.0% |
| B_dam_production | dam_foals_before | 100.0% |
| B_dam_production | dam_foals_aged3 | 100.0% |
| B_dam_production | dam_prog_pct_raced | 36.5% |
| B_dam_production | dam_prog_pct_won | 36.5% |
| B_dam_production | dam_prog_sw_per_foal | 36.5% |
| B_dam_production | dam_age_at_foaling | 48.6% |
| D_broodmare_sire | damsire_rel | 100.0% |
| D_broodmare_sire | damsire_missing | 100.0% |
| D_broodmare_sire | log_bms_fee_conception | 28.4% |
| D_broodmare_sire | log_bms_fee_initial | 52.4% |
| D_broodmare_sire | log_bms_fee_highest | 52.4% |
| D_broodmare_sire | log_bms_fee_latest | 52.4% |
| D_broodmare_sire | bms_fee_latest_vs_initial | 52.4% |
| D_broodmare_sire | bms_fee_years_listed | 52.4% |
| E_pedigree | nick | 100.0% |
| E_pedigree | dam_pedigree_completeness | 100.0% |
| F_progression | sale_level | 100.0% |
| F_progression | sale_new | 100.0% |
| F_progression | market_trend | 100.0% |
| F_progression | sire_last_year_rel | 89.8% |
| F_progression | sire_last_year_median_lp | 89.8% |
| F_progression | sire_trend | 69.0% |
| F_progression | bms_last_year_rel | 40.0% |
| F_progression | bms_last_year_median_lp | 40.0% |
| F_progression | bms_trend | 36.2% |
| F_progression | market_median_lp_last_year | 96.6% |
| G_horse_sale | weanling | 100.0% |
| G_horse_sale | filly | 100.0% |
| G_horse_sale | hip_signal | 100.0% |
| G_horse_sale | hip_pct | 100.0% |
| G_horse_sale | sale_month_f | 93.1% |
| G_horse_sale | venue_keeneland | 100.0% |
| G_horse_sale | venue_fasig_tipton | 100.0% |
| G_horse_sale | venue_obs | 100.0% |
| G_horse_sale | x_filly_yearling | 100.0% |
| C_dam_race_record | dam_record_found | 100.0% |
| C_dam_race_record | dam_starts | 48.6% |
| C_dam_race_record | dam_wins | 48.6% |
| C_dam_race_record | dam_earn | 12.8% |
| C_dam_race_record | dam_sw | 48.6% |
| C_dam_race_record | dam_gsw | 48.6% |
| C_dam_race_record | dam_g1w | 48.6% |
| C_dam_race_record | dam_best_esf | 11.4% |
| C_dam_race_record | dam_raced | 48.6% |
| X_interactions | x_sirefee_damrel | 85.0% |
| X_interactions | x_sirefee_bmsfee | 47.8% |

## Validation design

Time-based: train ≤ 2018, early stopping 2019–2020, interval calibration 2021–2022, test 2023–2025. Sold lots only (RNAs are censored and kept for the Tobit model in docs/sales-model.md). Group-aware check: test sales whose dam had no sale in the training years.

## Fit and baselines (log price)

| model / set | n | r2 | adj_r2 | mae | rmse | medae | residual_sd | median_abs_pct | medae_usd |
|---|---|---|---|---|---|---|---|---|---|
| baseline: sale_category_median | 20,760 | 0.188 |  | 1.100 | 1.363 | 0.944 | 1.363 | 75% | 38,000 |
| baseline: sire_year_mean | 20,760 | 0.340 |  | 0.959 | 1.228 | 0.778 | 1.221 | 66% | 34,404 |
| baseline: sire_year_median | 20,760 | 0.322 |  | 0.969 | 1.246 | 0.783 | 1.231 | 67% | 35,000 |
| baseline: comparable_sales | 20,760 | 0.335 |  | 0.959 | 1.233 | 0.771 | 1.214 | 67% | 35,217 |
| baseline: regression (sire fee + sex + age + sale level) | 20,760 | 0.386 | 0.385 | 0.944 | 1.185 | 0.800 | 1.184 | 64% | 30,342 |
| ridge (all features): train | 124,401 | 0.550 | 0.550 | 0.833 | 1.054 | 0.695 | 1.054 | 59% | 14,994 |
| ridge (all features): valid | 12,392 | 0.568 | 0.564 | 0.838 | 1.066 | 0.688 | 1.059 | 60% | 16,912 |
| ridge (all features): test | 20,760 | 0.572 | 0.570 | 0.779 | 0.989 | 0.646 | 0.986 | 55% | 24,354 |
| lightgbm (all features): train | 124,401 | 0.661 |  | 0.720 | 0.915 | 0.599 | 0.915 | 53% | 13,023 |
| lightgbm (all features): valid | 12,392 | 0.599 |  | 0.806 | 1.027 | 0.667 | 1.026 | 58% | 15,966 |
| lightgbm (all features): calib | 13,573 | 0.562 |  | 0.753 | 0.946 | 0.632 | 0.925 | 54% | 21,099 |
| lightgbm (all features): test | 20,760 | 0.574 |  | 0.771 | 0.987 | 0.630 | 0.987 | 55% | 26,597 |
| lightgbm: test, dams unseen in training | 15,033 | 0.577 |  | 0.772 | 0.991 | 0.629 | 0.990 | 55% | 26,557 |
| lightgbm: test, dams seen in training | 5,727 | 0.565 |  | 0.770 | 0.979 | 0.634 | 0.979 | 55% | 26,764 |

Adjusted R² is shown for the linear models only; for gradient boosting the parameter count is not meaningful, so out-of-sample R² on later years is the measure.

## Prediction intervals (80%, test years)

| method | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|
| group-normalized conformal | 79.6% | 2.433 | 10.61 |
| single-width conformal | 79.6% | 2.432 | 11.38 |
| conformalized quantile regression | 80.9% | 2.535 | 13.35 |

Width ratio = upper / lower bound in dollars. Group-normalized intervals are wider where the model has erred more on held-out sales (new sire, unproven dam, missing fee):

| segment | median |error| (log) |
|---|---|
| Y|sire_few|dam_unproven|nofee | 0.803 |
| Y|sire_few|dam_unproven|fee | 0.802 |
| Y|sire_few|dam_sold_before|fee | 0.711 |
| Y|sire_few|dam_sold_before|nofee | 0.675 |
| Y|sire_many|dam_sold_before|nofee | 0.662 |
| Y|sire_many|dam_unproven|fee | 0.654 |
| Y|sire_many|dam_sold_before|fee | 0.618 |
| W|sire_new|dam_sold_before|fee | 0.582 |
| W|sire_many|dam_sold_before|fee | 0.544 |
| W|sire_many|dam_unproven|fee | 0.524 |

By the price the model predicted (the honest view of interval width: grouping by the actual price conditions on the outcome, so extreme actual prices always look under-covered):

| predicted price band | n | conformal coverage | conformal median_width_ratio | CQR coverage | CQR median_width_ratio |
|---|---|---|---|---|---|
| $10-50k | 8,126 | 76.0% | 10.61 | 82.8% | 18.16 |
| $150-500k | 2,843 | 88.8% | 10.61 | 79.7% | 6.74 |
| $50-150k | 7,323 | 81.0% | 10.61 | 79.2% | 9.70 |
| $500k+ | 195 | 90.3% | 10.61 | 80.5% | 6.47 |
| <$10k | 2,273 | 75.1% | 10.61 | 80.6% | 17.53 |

## Interaction search (Phase 12.4, ridge, one product term at a time)

| interaction | rows with both | held-out r2 gain | t (train) |
|---|---|---|---|
| log_sire_fee_conception x weanling | 103,283 | +0.0025 | 5.2 |
| dam_pedigree_completeness x weanling | 124,401 | +0.0013 | 4.8 |
| log_sire_fee_conception x dam_rel | 103,283 | +0.0005 | -4.2 |
| log_sire_fee_conception x dam_starts | 49,982 | +0.0005 | -1.1 |
| dam_starts x dam_pedigree_completeness | 57,226 | +0.0003 | -3.2 |
| log_sire_fee_conception x log_bms_fee_highest | 49,313 | +0.0001 | 0.7 |
| sire_rel x damsire_rel | 124,401 | +0.0001 | -2.9 |
| dam_rel x damsire_rel | 124,401 | +0.0000 | -5.4 |
| log_sire_fee_conception x filly | 103,283 | +0.0000 | 0.3 |
| filly x weanling | 124,401 | +0.0000 | 2.4 |
| sire_trend x market_trend | 84,785 | -0.0001 | -5.7 |
| log_bms_fee_highest x bms_trend | 27,435 | -0.0003 | -0.5 |
| sale_level x log_sire_fee_conception | 103,283 | -0.0003 | 3.5 |

Gradient boosting already models interactions; a term is worth keeping in an interpretable model only if it raises held-out R2, not just when its training t-stat is large.

## Performance by segment (test years, LightGBM)

### sale_year

| sale_year | n | r2 | mae | bias | median_abs_pct | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|---|---|---|---|---|
| 2023.000 | 6547.000 | 0.569 | 0.767 | -0.039 | 54% | 79.6% | 2.427 | 10.61 |
| 2024.000 | 6412.000 | 0.590 | 0.767 | -0.071 | 55% | 79.3% | 2.410 | 10.61 |
| 2025.000 | 7801.000 | 0.556 | 0.779 | 0.033 | 55% | 79.7% | 2.458 | 10.61 |

### venue

| venue | n | r2 | mae | bias | median_abs_pct | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|---|---|---|---|---|
| fasig_tipton | 7,058 | 0.574 | 0.791 | 0.090 | 55% | 78.7% | 2.455 | 10.61 |
| keeneland | 13,702 | 0.557 | 0.761 | -0.079 | 55% | 80.0% | 2.422 | 10.61 |

### kind

| kind | n | r2 | mae | bias | median_abs_pct | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|---|---|---|---|---|
| W | 2,227 | 0.572 | 0.715 | 0.096 | 51% | 77.6% | 2.172 | 8.00 |
| Y | 18,533 | 0.573 | 0.778 | -0.036 | 55% | 79.8% | 2.465 | 10.61 |

### sex

| sex | n | r2 | mae | bias | median_abs_pct | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|---|---|---|---|---|
| colt | 11,353 | 0.572 | 0.767 | -0.022 | 54% | 80.0% | 2.431 | 10.61 |
| filly | 9,407 | 0.571 | 0.777 | -0.022 | 55% | 79.0% | 2.436 | 10.61 |

### price_band

| price_band | n | r2 | mae | bias | median_abs_pct | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|---|---|---|---|---|
| $10-50k | 7,006 | -2.502 | 0.678 | -0.141 | 55% | 85.6% | 2.440 | 10.61 |
| $150-500k | 3,807 | -5.944 | 0.714 | 0.629 | 49% | 83.2% | 2.414 | 10.61 |
| $50-150k | 5,246 | -5.185 | 0.599 | 0.335 | 42% | 87.3% | 2.422 | 10.61 |
| $500k+ | 800 | -7.298 | 0.957 | 0.953 | 59% | 69.8% | 2.431 | 10.61 |
| <$10k | 3,901 | -3.901 | 1.190 | -1.122 | 188% | 56.8% | 2.455 | 10.61 |

### fee_known

| fee_known | n | r2 | mae | bias | median_abs_pct | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|---|---|---|---|---|
| sire fee known | 18,834 | 0.578 | 0.768 | -0.021 | 54% | 79.6% | 2.421 | 10.61 |
| sire fee missing | 1,926 | 0.501 | 0.808 | -0.028 | 58% | 79.3% | 2.556 | 12.56 |

### dam_record

| dam_record | n | r2 | mae | bias | median_abs_pct | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|---|---|---|---|---|
| dam race record found | 10,988 | 0.597 | 0.752 | -0.007 | 53% | 80.6% | 2.428 | 10.61 |
| no dam race record | 9,772 | 0.534 | 0.793 | -0.038 | 57% | 78.4% | 2.440 | 10.61 |

### bms_fee

| bms_fee | n | r2 | mae | bias | median_abs_pct | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|---|---|---|---|---|
| bms fee known | 14,411 | 0.592 | 0.763 | 0.012 | 53% | 80.1% | 2.437 | 10.61 |
| bms fee missing | 6,349 | 0.530 | 0.791 | -0.098 | 57% | 78.3% | 2.424 | 10.61 |

### sire (12 most-sold)

| sire | n | r2 | mae | bias | median_abs_pct | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|---|---|---|---|---|
| Authentic | 196 | 0.504 | 0.688 | -0.048 | 48% | 83.7% | 2.517 | 12.15 |
| Into Mischief | 196 | 0.594 | 0.614 | 0.017 | 47% | 87.2% | 2.389 | 10.61 |
| Liam's Map | 213 | 0.250 | 0.659 | 0.092 | 48% | 89.7% | 2.378 | 10.61 |
| Maclean's Music | 238 | 0.090 | 0.795 | -0.185 | 58% | 79.8% | 2.346 | 10.61 |
| McKinzie | 263 | 0.113 | 0.751 | -0.016 | 53% | 79.8% | 2.330 | 10.61 |
| Munnings | 207 | 0.318 | 0.607 | 0.007 | 45% | 88.9% | 2.371 | 10.61 |
| Not This Time | 211 | 0.343 | 0.663 | -0.038 | 45% | 82.9% | 2.378 | 10.61 |
| Omaha Beach | 203 | 0.149 | 0.753 | -0.106 | 53% | 77.3% | 2.345 | 10.61 |
| Practical Joke | 238 | 0.036 | 0.678 | 0.119 | 49% | 81.5% | 2.349 | 10.61 |
| Uncle Mo | 225 | 0.256 | 0.687 | -0.205 | 50% | 86.2% | 2.375 | 10.61 |
| Vekoma | 206 | 0.184 | 0.698 | 0.072 | 49% | 84.0% | 2.350 | 10.61 |
| Yaupon | 247 | -0.007 | 0.693 | 0.349 | 52% | 82.6% | 2.354 | 10.61 |

### broodmare sire (12 most-sold)

| damsire | n | r2 | mae | bias | median_abs_pct | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|---|---|---|---|---|
|  | 13,702 | 0.557 | 0.761 | -0.079 | 55% | 80.0% | 2.422 | 10.61 |
| BERNARDINI | 112 | 0.665 | 0.720 | 0.027 | 52% | 82.1% | 2.417 | 10.61 |
| CANDY RIDE (ARG) | 111 | 0.449 | 0.838 | 0.074 | 58% | 77.5% | 2.470 | 11.19 |
| HARD SPUN | 92 | 0.521 | 0.816 | 0.003 | 50% | 77.2% | 2.486 | 11.19 |
| INTO MISCHIEF | 113 | 0.501 | 0.740 | -0.001 | 50% | 77.9% | 2.539 | 12.15 |
| MALIBU MOON | 151 | 0.551 | 0.781 | 0.093 | 54% | 77.5% | 2.419 | 10.61 |
| MEDAGLIA D'ORO | 156 | 0.687 | 0.685 | 0.161 | 49% | 84.6% | 2.431 | 10.61 |
| MORE THAN READY | 96 | 0.565 | 0.818 | 0.001 | 62% | 77.1% | 2.495 | 11.19 |
| SPEIGHTSTOWN | 102 | 0.599 | 0.788 | 0.180 | 51% | 73.5% | 2.463 | 10.61 |
| TAPIT | 158 | 0.604 | 0.842 | 0.147 | 57% | 76.6% | 2.441 | 10.61 |
| TIZNOW | 103 | 0.554 | 0.860 | 0.133 | 61% | 72.8% | 2.449 | 10.61 |
| UNCLE MO | 108 | 0.567 | 0.779 | 0.209 | 53% | 78.7% | 2.435 | 10.61 |

## What each feature group adds (drop one group, refit, score test years)

| group dropped | features | r2 lost (lightgbm) | r2 lost (ridge) | mae added (lightgbm) |
|---|---|---|---|---|
| G_horse_sale | 9 | +0.1146 | +0.0943 | +0.0877 |
| F_progression | 10 | +0.0169 | +0.0950 | +0.0396 |
| A_sire | 18 | +0.0021 | +0.0163 | +0.0069 |
| E_pedigree | 2 | +0.0010 | +0.0120 | +0.0073 |
| B_dam_production | 16 | -0.0062 | +0.0035 | -0.0046 |
| X_interactions | 2 | -0.0102 | +0.0005 | -0.0076 |
| D_broodmare_sire | 8 | -0.0132 | +0.0003 | -0.0126 |
| C_dam_race_record | 9 | -0.0134 | +0.0001 | -0.0092 |

Positive = the group helps on later years. Small negatives are noise: those features are redundant with others, not harmful.

## Broodmare-sire fee: highest vs latest vs at conception (Phase 12.2 D)

| broodmare-sire fee used | test r2 | test mae |
|---|---|---|
| none | 0.599 | 0.751 |
| highest | 0.582 | 0.764 |
| latest | 0.582 | 0.764 |
| at conception | 0.582 | 0.764 |

## Main contributing features (mean |SHAP| on test sales, log-price units)

| group | mean |SHAP| |
|---|---|
| F_progression | 0.692 |
| A_sire | 0.596 |
| G_horse_sale | 0.594 |
| B_dam_production | 0.208 |
| E_pedigree | 0.115 |
| D_broodmare_sire | 0.063 |
| X_interactions | 0.015 |
| C_dam_race_record | 0.009 |

| feature | mean |SHAP| |
|---|---|
| sale_level | 0.420 |
| log_sire_fee_latest | 0.363 |
| hip_signal | 0.194 |
| sire_last_year_median_lp | 0.168 |
| hip_pct | 0.163 |
| sale_month_f | 0.117 |
| dam_pedigree_completeness | 0.095 |
| dam_rel | 0.089 |
| filly | 0.076 |
| dam_foals_before | 0.039 |
| bms_fee_years_listed | 0.032 |
| sire_last_year_rel | 0.032 |
| sire_rel | 0.031 |
| fee_momentum | 0.030 |
| dam_age_at_foaling | 0.028 |
| sire_prog_win_rate | 0.028 |
| venue_keeneland | 0.023 |
| bms_trend | 0.022 |
| sire_fee_latest_vs_initial | 0.021 |
| sire_fee_years_listed | 0.021 |
| nick | 0.020 |
| sire_prog_earn_per_runner | 0.019 |
| sire_log_n | 0.017 |
| dam_prog_earnings | 0.017 |
| log_fee_conception_hist | 0.015 |

SHAP and drop-one results measure predictive contribution, not causal effect: sire fee and sale level, for example, partly reflect market judgments of the same horse.

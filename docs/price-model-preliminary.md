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

## Leakage check

Features for a sale year rebuilt from source tables cut off at that year (later fees, races, rankings, sales and this year's prices removed) and compared with the full build:

| year | rows | features | mismatched_features | mismatched_cells |
|---|---|---|---|---|
| 2,012 | 400 | 74 | none | 0 |
| 2,018 | 400 | 74 | none | 0 |
| 2,024 | 400 | 74 | none | 0 |

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
| ridge (all features): train | 124,401 | 0.550 | 0.550 | 0.833 | 1.054 | 0.695 | 1.054 | 59% | 14,992 |
| ridge (all features): valid | 12,392 | 0.568 | 0.564 | 0.838 | 1.066 | 0.688 | 1.059 | 60% | 16,908 |
| ridge (all features): test | 20,760 | 0.572 | 0.570 | 0.779 | 0.989 | 0.646 | 0.986 | 55% | 24,374 |
| lightgbm (all features): train | 124,401 | 0.660 |  | 0.720 | 0.916 | 0.600 | 0.916 | 53% | 13,019 |
| lightgbm (all features): valid | 12,392 | 0.600 |  | 0.805 | 1.026 | 0.663 | 1.025 | 58% | 15,893 |
| lightgbm (all features): calib | 13,573 | 0.566 |  | 0.750 | 0.943 | 0.631 | 0.921 | 54% | 20,866 |
| lightgbm (all features): test | 20,760 | 0.570 |  | 0.775 | 0.992 | 0.632 | 0.992 | 55% | 26,594 |
| lightgbm: test, dams unseen in training | 15,033 | 0.573 |  | 0.776 | 0.995 | 0.630 | 0.995 | 55% | 26,593 |
| lightgbm: test, dams seen in training | 5,727 | 0.562 |  | 0.772 | 0.982 | 0.638 | 0.982 | 55% | 26,597 |

Adjusted R² is shown for the linear models only; for gradient boosting the parameter count is not meaningful, so out-of-sample R² on later years is the measure.

## Prediction intervals (80%, test years)

| method | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|
| group-normalized conformal | 79.1% | 2.425 | 10.61 |
| single-width conformal | 79.3% | 2.424 | 11.29 |

Width ratio = upper / lower bound in dollars. Group-normalized intervals are wider where the model has erred more on held-out sales (new sire, unproven dam, missing fee):

| segment | median |error| (log) |
|---|---|
| Y|sire_few|dam_unproven|nofee | 0.792 |
| Y|sire_few|dam_unproven|fee | 0.777 |
| Y|sire_few|dam_sold_before|fee | 0.709 |
| Y|sire_few|dam_sold_before|nofee | 0.681 |
| Y|sire_many|dam_sold_before|nofee | 0.672 |
| Y|sire_many|dam_unproven|fee | 0.648 |
| Y|sire_many|dam_sold_before|fee | 0.619 |
| W|sire_new|dam_sold_before|fee | 0.566 |
| W|sire_many|dam_unproven|fee | 0.549 |
| W|sire_many|dam_sold_before|fee | 0.533 |

## Performance by segment (test years, LightGBM)

### sale_year

| sale_year | n | r2 | mae | bias | median_abs_pct | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|---|---|---|---|---|
| 2023.000 | 6547.000 | 0.567 | 0.768 | -0.041 | 54% | 79.2% | 2.418 | 10.61 |
| 2024.000 | 6412.000 | 0.587 | 0.771 | -0.065 | 55% | 78.6% | 2.401 | 10.61 |
| 2025.000 | 7801.000 | 0.551 | 0.783 | 0.030 | 55% | 79.3% | 2.450 | 10.61 |

### venue

| venue | n | r2 | mae | bias | median_abs_pct | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|---|---|---|---|---|
| fasig_tipton | 7,058 | 0.571 | 0.796 | 0.117 | 55% | 78.3% | 2.446 | 10.61 |
| keeneland | 13,702 | 0.553 | 0.764 | -0.093 | 55% | 79.5% | 2.414 | 10.61 |

### kind

| kind | n | r2 | mae | bias | median_abs_pct | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|---|---|---|---|---|
| W | 2,227 | 0.573 | 0.713 | 0.093 | 51% | 77.3% | 2.160 | 8.12 |
| Y | 18,533 | 0.568 | 0.782 | -0.035 | 55% | 79.3% | 2.457 | 10.61 |

### sex

| sex | n | r2 | mae | bias | median_abs_pct | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|---|---|---|---|---|
| colt | 11,353 | 0.571 | 0.769 | -0.015 | 54% | 79.7% | 2.423 | 10.61 |
| filly | 9,407 | 0.564 | 0.782 | -0.030 | 55% | 78.4% | 2.428 | 10.61 |

### price_band

| price_band | n | r2 | mae | bias | median_abs_pct | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|---|---|---|---|---|
| $10-50k | 7,006 | -2.548 | 0.683 | -0.143 | 55% | 84.9% | 2.431 | 10.61 |
| $150-500k | 3,807 | -5.988 | 0.713 | 0.630 | 48% | 83.0% | 2.407 | 10.61 |
| $50-150k | 5,246 | -5.273 | 0.602 | 0.336 | 42% | 87.1% | 2.414 | 10.61 |
| $500k+ | 800 | -7.342 | 0.961 | 0.957 | 59% | 69.0% | 2.424 | 10.61 |
| <$10k | 3,901 | -3.926 | 1.193 | -1.121 | 190% | 56.2% | 2.446 | 10.61 |

### fee_known

| fee_known | n | r2 | mae | bias | median_abs_pct | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|---|---|---|---|---|
| sire fee known | 18,834 | 0.573 | 0.772 | -0.018 | 55% | 79.0% | 2.411 | 10.61 |
| sire fee missing | 1,926 | 0.501 | 0.803 | -0.053 | 58% | 79.6% | 2.566 | 13.00 |

### dam_record

| dam_record | n | r2 | mae | bias | median_abs_pct | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|---|---|---|---|---|
| dam race record found | 10,988 | 0.593 | 0.756 | -0.002 | 53% | 80.1% | 2.420 | 10.61 |
| no dam race record | 9,772 | 0.530 | 0.797 | -0.044 | 57% | 77.9% | 2.431 | 10.61 |

### bms_fee

| bms_fee | n | r2 | mae | bias | median_abs_pct | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|---|---|---|---|---|
| bms fee known | 14,411 | 0.588 | 0.767 | 0.021 | 54% | 79.6% | 2.429 | 10.61 |
| bms fee missing | 6,349 | 0.526 | 0.792 | -0.118 | 58% | 77.9% | 2.416 | 10.61 |

### sire (12 most-sold)

| sire | n | r2 | mae | bias | median_abs_pct | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|---|---|---|---|---|
| Authentic | 196 | 0.512 | 0.684 | -0.039 | 48% | 83.7% | 2.506 | 11.89 |
| Into Mischief | 196 | 0.597 | 0.611 | 0.017 | 47% | 86.7% | 2.383 | 10.61 |
| Liam's Map | 213 | 0.254 | 0.652 | 0.069 | 48% | 87.8% | 2.372 | 10.61 |
| Maclean's Music | 238 | 0.070 | 0.809 | -0.194 | 59% | 77.3% | 2.346 | 10.61 |
| McKinzie | 263 | 0.096 | 0.758 | -0.010 | 54% | 78.7% | 2.328 | 10.61 |
| Munnings | 207 | 0.293 | 0.618 | -0.019 | 46% | 88.4% | 2.366 | 10.61 |
| Not This Time | 211 | 0.341 | 0.669 | -0.002 | 45% | 81.5% | 2.374 | 10.61 |
| Omaha Beach | 203 | 0.169 | 0.747 | -0.095 | 51% | 76.8% | 2.339 | 10.61 |
| Practical Joke | 238 | 0.043 | 0.677 | 0.124 | 49% | 82.4% | 2.344 | 10.61 |
| Uncle Mo | 225 | 0.257 | 0.689 | -0.205 | 51% | 86.2% | 2.371 | 10.61 |
| Vekoma | 206 | 0.185 | 0.695 | 0.054 | 48% | 83.0% | 2.341 | 10.61 |
| Yaupon | 247 | -0.016 | 0.695 | 0.336 | 51% | 82.2% | 2.345 | 10.61 |

### broodmare sire (12 most-sold)

| damsire | n | r2 | mae | bias | median_abs_pct | coverage | mean_width_log | median_width_ratio |
|---|---|---|---|---|---|---|---|---|
|  | 13,702 | 0.553 | 0.764 | -0.093 | 55% | 79.5% | 2.414 | 10.61 |
| BERNARDINI | 112 | 0.667 | 0.715 | 0.041 | 52% | 82.1% | 2.407 | 10.61 |
| CANDY RIDE (ARG) | 111 | 0.439 | 0.847 | 0.104 | 57% | 77.5% | 2.462 | 11.11 |
| HARD SPUN | 92 | 0.516 | 0.825 | 0.027 | 51% | 76.1% | 2.477 | 11.11 |
| INTO MISCHIEF | 113 | 0.495 | 0.746 | 0.018 | 50% | 77.9% | 2.521 | 11.89 |
| MALIBU MOON | 151 | 0.531 | 0.802 | 0.121 | 52% | 76.8% | 2.412 | 10.61 |
| MEDAGLIA D'ORO | 156 | 0.685 | 0.691 | 0.198 | 50% | 83.3% | 2.426 | 10.61 |
| MORE THAN READY | 96 | 0.550 | 0.834 | 0.041 | 62% | 77.1% | 2.484 | 11.11 |
| SPEIGHTSTOWN | 102 | 0.585 | 0.799 | 0.206 | 51% | 75.5% | 2.452 | 10.61 |
| TAPIT | 158 | 0.600 | 0.845 | 0.189 | 58% | 78.5% | 2.434 | 10.61 |
| TIZNOW | 103 | 0.547 | 0.869 | 0.170 | 60% | 70.9% | 2.438 | 10.61 |
| UNCLE MO | 108 | 0.563 | 0.780 | 0.238 | 53% | 78.7% | 2.423 | 10.61 |

## What each feature group adds (drop one group, refit, score test years)

| group dropped | features | r2 lost (lightgbm) | r2 lost (ridge) | mae added (lightgbm) |
|---|---|---|---|---|
| G_horse_sale | 9 | +0.1149 | +0.0943 | +0.0874 |
| F_progression | 10 | +0.0162 | +0.0951 | +0.0387 |
| A_sire | 18 | +0.0023 | +0.0163 | +0.0079 |
| E_pedigree | 2 | +0.0005 | +0.0119 | +0.0068 |
| B_dam_production | 16 | -0.0069 | +0.0035 | -0.0057 |
| X_interactions | 2 | -0.0097 | +0.0005 | -0.0066 |
| D_broodmare_sire | 8 | -0.0134 | +0.0003 | -0.0126 |
| C_dam_race_record | 9 | -0.0140 | +0.0001 | -0.0095 |

Positive = the group helps on later years. Small negatives are noise: those features are redundant with others, not harmful.

## Broodmare-sire fee: highest vs latest vs at conception (Phase 12.2 D)

| broodmare-sire fee used | test r2 | test mae |
|---|---|---|
| none | 0.598 | 0.751 |
| highest | 0.581 | 0.764 |
| latest | 0.583 | 0.763 |
| at conception | 0.583 | 0.763 |

## Main contributing features (mean |SHAP| on test sales, log-price units)

| group | mean |SHAP| |
|---|---|
| F_progression | 0.704 |
| G_horse_sale | 0.594 |
| A_sire | 0.589 |
| B_dam_production | 0.206 |
| E_pedigree | 0.118 |
| D_broodmare_sire | 0.066 |
| X_interactions | 0.015 |
| C_dam_race_record | 0.009 |

| feature | mean |SHAP| |
|---|---|
| sale_level | 0.427 |
| log_sire_fee_latest | 0.358 |
| hip_signal | 0.198 |
| sire_last_year_median_lp | 0.171 |
| hip_pct | 0.158 |
| sale_month_f | 0.121 |
| dam_pedigree_completeness | 0.098 |
| dam_rel | 0.087 |
| filly | 0.073 |
| dam_foals_before | 0.040 |
| sire_rel | 0.033 |
| bms_fee_years_listed | 0.033 |
| fee_momentum | 0.030 |
| sire_prog_win_rate | 0.029 |
| sire_last_year_rel | 0.028 |
| dam_age_at_foaling | 0.027 |
| venue_keeneland | 0.024 |
| sire_fee_latest_vs_initial | 0.023 |
| bms_trend | 0.023 |
| sire_fee_years_listed | 0.022 |
| nick | 0.020 |
| sire_prog_earn_per_runner | 0.018 |
| dam_prog_earnings | 0.016 |
| market_median_lp_last_year | 0.016 |
| dam_log_n | 0.014 |

SHAP and drop-one results measure predictive contribution, not causal effect: sire fee and sale level, for example, partly reflect market judgments of the same horse.

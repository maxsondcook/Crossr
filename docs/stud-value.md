# Colt breeding value: comparable stallions

Replaces the colt path in `ValueProjector.py` that summed the sons of the colt's
sire's sire (Instagrand colt → Into Mischief's sons, $13,830–$1,084,043). Generated
numbers: [stud-value-results.md](stud-value-results.md).

- Runtime: `crossr_core/stud_value.py` (`colt_value`), used by `ValueProjector.project_colt_bv`
- Training: `scripts/train_stud_value.py --save` → `crossr_models` row `stud_value`
  and `Analyzed Sales/stud_value_model.json.gz` (published by `scripts/load_railway.py --only models`)

## What is measured

A colt's breeding value is what his sire's colts are worth at stud, per colt:

    Σ (initial stud fee of each son that went to stud × 400) / sire's colts

- **×400** is the project's lifetime-stud-value rule (kept by decision); it is
  defined once, `stud_value.STUD_DEAL_MULTIPLIER`.
- **Colts** = half the live foals in the sire's crops at least 8 years old (old
  enough for sons to have retired to stud), from `breeding_seasons`. The old code
  divided by one season's runners (376 for Into Mischief; his real count is 2,431 foals).
- **Sons at stud**: stallions in `breeding_seasons` or `stud_fees` whose sire is
  him (`race_horses`). About half have no fee on file; their initial fee is
  estimated from their first-season book (fitted on sons with a fee: r = 0.66).
- `breeding_seasons` lists some stallions under numbered names in some years
  ("Into Mischief (26)"); those are merged. An unrelated older stallion with the
  same name shows up as seasons before a 3+ year gap and is split off.

## How a sire without mature crops is valued

From stallions that looked like him **at the same point in their career**: a
two-part model, fitted separately for each career stage (years since first season,
1–12):

1. chance any son reaches stud (logistic), and
2. size of the value when some do (log-normal),

on **initial stud fee** and **how his fee has moved since** (log of fee at that
stage ÷ initial fee). At stage 5 both are strongly significant in both parts
(p < 10⁻¹¹). Expected value = P(any) × E[size]; the **p25–p75 range** is the same
quantity's spread among such stallions, so it includes $0 whenever fewer than 75%
of them got a son to stud.

Once a sire has mature crops, his own record takes over, weighted
colts / (colts + k). k was fitted on held-out stallions (partial record ten years in
vs. final outcome) and came out at the smallest value tried (k = 1): even one or
two mature crops predict a sire's final record better than the comparison does.

There is **no sire's-sire fallback**: a sire with no initial fee and no mature
crops gets no breeding value.

Each colt page lists the five nearest comparable stallions (same initial fee and
fee path at the same stage) with their realized value per colt.

## Validation

Stallions who started at stud 2006–2011, predicted by a model trained on those
who started by 2005, using only their fee history up to the stage shown:

| Stage | Spearman with actual | p | Sire's-sire rule |
|---|---|---|---|
| 2 | 0.47 | 10⁻¹⁴ | −0.03 |
| 5 | 0.53 | 10⁻¹⁹ | −0.03 |
| 8 | 0.53 | 10⁻¹⁹ | −0.03 |

The sire's-sire rule has no predictive value. The model's totals run 0.68–0.90 of
actual on the held-out stallions (it under-predicts somewhat).

Candidates rejected by the agreed rule (p < 0.01 **and** better held-out fit):

- **Cohort** (year he started at stud): p = 0.001 but worse held-out fit.
- **Pedigree similarity** (outcomes of the 15 most pedigree-similar stallions,
  using the app's 5-generation slot similarity): p = 0.46, worse held-out fit.
  Tested on the 285 of 448 stallions with pedigree trees; worth re-testing once
  the pedigree scrape fills in the rest.

## Fillies and mares

Same "one quantity on both ends" rule:

- Filly by a broodmare sire: expected foals (7) × p25 / p75 foal price of mares
  by that sire; point = 7 × mean price. A thin broodmare sire pools up to five
  stallions with the nearest initial fee and race record instead of borrowing one.
- Proven mare: realized sales + remaining expected foals × p25 / p75 price
  (≥ 5 sales), or × mean price for 5.6–8.4 expected foals (fewer sales).

## Retraining

```bash
scripts/pipeline/railway_env.sh crossr_dev .venv/bin/python scripts/train_stud_value.py --save
scripts/pipeline/railway_env.sh railway .venv/bin/python scripts/load_railway.py --only models
```

Needs scipy (`requirements-model.txt`). Takes about a minute.

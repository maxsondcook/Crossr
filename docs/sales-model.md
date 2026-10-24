# Sales model: expected sale price and Boom%

Fitted, validated replacement for the fee-band "Projected Price" on yearling and
weanling lots. Full generated tables (every coefficient, CI, p-value, year-by-year
held-out scores, calibration) are in [sales-model-results.md](sales-model-results.md).

- Runtime: `crossr_core/sales_model.py` (pure Python, ~12 µs per lot)
- Training: `scripts/train_sales_model.py` → `Analyzed Sales/sales_model.json.gz`
- Wiring: `crossr_core/projections.py::project_lot_market`
  (set `CROSSR_SALES_MODEL=0` to fall back to the fee bands)

## What was agreed

| Output | Definition | Status |
|---|---|---|
| Expected sale price | Hammer price if the lot sells | Built |
| Boom% | P(wins a graded / Group race anywhere in the world) | Built |
| Bust% | P(never starts) | Waiting on dam produce records |
| Value (fair price) | PV at 7%/yr of expected gross race earnings + mean breeding value | Waiting on dam produce records |

RNAs are treated as censored (the horse was worth less than the reserve it failed
to reach); outs are dropped. Private sales are not in the data.

## Data

`sales_lots` youngstock (catalog year − birth year = 0 or 1), 1999–2026: 184,499
lots (166,537 sold, 17,962 RNA with a price). Stud fees from `stud_fees` (2001+;
only ~47% of lots have a conception-year fee). Graded results from
`graded_stakes`, linked to sire/dam/foal year through `race_horses` (99.9% of
graded winners link), giving 1,606 graded winners among 145,752 youngstock horses
from the 1998–2021 crops.

## No look-ahead

Every feature is computed **as of the sale**: `History` replays the sales year by
year and a lot only sees earlier years' sales and graded results. The app uses
the same object (its final state is the artifact), and training asserts that
runtime features reproduce training features exactly (max difference 0).

## Features (candidates)

Sale level (last year's average log price at this sale), sex, weanling, sire stud
fee at conception (+ missing flag), fee change from conception to sale, sire /
damsire / dam earlier-foal prices relative to their sale (empirical-Bayes shrunk;
k estimated from pre-2010 data: sire 2.3, dam 1.8, damsire 7.9), sire × damsire
cross (nick) residual, counts of earlier foals and graded winners/placed, dam's
own graded record, hip position within the catalog (proxy for book/session).

**Selection rule (agreed):** a feature (or pair, e.g. fee + missing flag) is kept
only if p < 0.01 with sire-clustered standard errors **and** dropping it lowers
held-out log-likelihood (train ≤ 2017, test 2018–2025). Market trend, weanling,
number of sire foals, missing damsire and dam's graded-winner/placed foal counts
failed for price.

## Models

**Price:** censored-normal (Tobit) regression of log price. Because the censored
fit prices every lot including buy-backs, lots that sell average 14% above it
(estimated from training residuals); the displayed figure is the expected hammer
**if it sells**, with the p25–p75 range (p10–p90 also returned). The censored
"fair value" is returned too.

**Boom%:** logistic regression on the same candidates. A crop is scored with a
model trained only on crops at least 4 years older (their outcomes were known).

Two variants of each: with hip position (catalog lots) and without (horse pages
that do not know the hip).

## Held-out accuracy

Rolling by sale year 2010–2025 (train on all earlier years, score the next):

| | With hip | No hip | Current fee bands |
|---|---|---|---|
| R² (log price) | **0.50** | 0.45 | — |
| R² on lots the fee bands can price (n=70,647) | **0.53** | 0.49 | 0.43 |
| Median absolute error | 60% | 63% | — |
| p25–p75 range contains price | 51.1% (target 50) | 50.8% | — |
| p10–p90 range contains price | 81.0% (target 80) | 81.1% | — |

Honest noise level: a single horse's 80% range is about ÷/× 4. The data has no
conformation, vet or consignor information for most lots, so most of the spread is
irreducible from what we hold. Remaining bias: prices run ~6% above prediction on
average, which is the market's year-over-year growth the model can't foresee.

Boom%, crops 2008–2021: AUC 0.68 (with hip) / 0.65; the top predicted decile
produced graded winners at 3.3% vs 0.45% in the bottom decile (base 1.2%), and
predicted rates match observed rates decile by decile.

## Key effects (price, with hip; all p ≤ 0.001)

- Filly: −18% vs colt
- Stud fee at conception: +10% fee → +2.5% price, on top of the sire's track record
  (the sire's earlier-foal prices carry most of the fee signal)
- Sire fee rising between conception and sale: +10% → +4.8%
- Dam herself graded winner: +16%; graded placed: +15%
- Hip position: lots at the end of a catalog sell for well under half of lots at the front
- Each sire / damsire / dam / cross track-record term is strongly positive (see results)

## Retraining

```bash
pip install -r requirements-model.txt
python scripts/train_sales_model.py
```

Needs the local CSV copies in `data/` (sales_lots, stud_fees, race_horses,
graded_stakes). Takes about a minute. Retrain after new sales are loaded; lots
from a sale already in the training data are flagged `in_sample`.

## Next

1. Bust% and Value once the dam produce records (every foal, starts, earnings,
   stud/broodmare outcome) land.
2. Re-run selection with the requested data: complete stud fees, book/session,
   catalog pedigree pages (foaling date, black type), Keeneland consignors.
3. The catalog price filter (`expected_market_mid_for_filter`) still uses fee bands.

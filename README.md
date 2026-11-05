# Crossr

Thoroughbred pedigree, stallion, sales, and mating research. A **Next.js** site (`web/`) on a **FastAPI** JSON API (`crossr_api/`), with all data in Postgres.

The browser only ever gets JSON from the API; raw catalogs and results never leave Postgres.

## What it does

- **Horse profiles** — 5-generation catalog pedigree, female family / produce, race record, and sections chosen by the horse's type (see [Horse identity and profile types](#horse-identity-and-profile-types)): stallions get stud fee and mares bred, rankings, progeny statistics, Top Progeny / **Best Broodmare Sire Crosses**, and a **Sales** panel; fillies, mares and broodmares get **Suggested Stallions**; colts get **Similar Active Stallions**; geldings get no breeding sections.
- **Stallion directory** — every stallion on The Jockey Club's current Report of Mares Bred (North America); filter by farm, crop, fee, and stud year; compare stallions; star horses into **My Barn**.
- **Hypomating** — given a broodmare, suggest stallions from graded-stakes winner crosses (surface + fee), then offer sons/ancestors when the proven sire is too expensive. Same-cross inbreeding is blocked (for example Citizen Bull is not re-suggested on Into Mischief × Distorted Humor).
- **Sales** — Fasig-Tipton (2004–) and Keeneland (1999–) catalogs: browse a sale, search a sire’s auction record, or look up one horse’s sale history.
- **Accounts** — register / sign in for saved preferences.

Horses are stored as `NAME (YYYY)`. If a search hits two or more foaling years, the app asks which horse you mean.

## Horse identity and profile types

Horses share names (two Englishmans, two Stage Magics), so nothing is joined by
name alone. `crossr_core/identity.py` decides whether stud data belongs to a horse
(sex, foaling year and sire must agree; the stallion's own foaling year and sire come
from the BloodHorse ranking lists) and classifies every horse:

| Profile type | Shown |
| --- | --- |
| `stallion` (active / inactive / pensioned / deceased / historical) | stud fee & mares bred, rankings, progeny statistics, Top Progeny ⇄ Best Broodmare Sire Crosses, Sales panel |
| `broodmare`, `racing_female` | pedigree, female family, race record, Suggested Stallions |
| `racing_male` (colt / horse / ridgling) | pedigree, female family, race record, Similar Active Stallions |
| `gelding` | pedigree, female family, race record only |

When a bare name matches two different horses the profile asks which foaling year.
Suggestions and similar-stallion tables use only stallions standing in North America
with a current fee (`identity.stands_in_north_america`); data for overseas stallions is
kept for later.

## Stallion sales panel

`GET /api/sales/sire/{name}/summary` (stallion profiles): average prices for
yearlings, weanlings and all horses for the current year (to date), the latest
completed year, the last three completed years and lifetime; an average-price-by-year
chart; a sale dropdown (only sales where he had progeny) with per-sale stats; and a
horse list filterable by sold status, type (age at sale), sex and broodmare sires.
Sold lots only (RNAs are not sales, outs are excluded); lots foaled before the
stallion entered stud are a namesake's and are dropped.

## Data on Railway

Crossr's data lives **only** in **Railway Postgres**: the API, the scrapers and the
training script all need `DATABASE_URL` (see `.env.example`), and nothing reads local
data files at runtime. Locally, use the `crossr_dev` database. What lives in which
table, loading and deployment: [`docs/RAILWAY.md`](docs/RAILWAY.md).

## Run locally

Python 3.11+ and Node 18+.

```bash
python3 -m pip install -r requirements.txt
export DATABASE_URL="postgresql://...:.../crossr_dev"   # see docs/RAILWAY.md
./scripts/run_api.sh                    # http://localhost:8000
```

```bash
cd web
npm install
npm run dev                             # http://localhost:3000
```

Docker: `docker compose up --build` (with `DATABASE_URL` set).

The terminal menus (`main.py`, hypomating, sales history, sale analyzer) are retired;
everything runs through the site.

## Horse profile panels

On `/horses/{name}`:

| Panel | Source |
| --- | --- |
| Pedigree + female family | `pedigrees` table; stakes status from `race_starts` (+ `graded_stakes`) |
| Stud fee & mares bred | `stud_fees`, `breeding_seasons` tables |
| **Stallion rankings** | `stallion_rankings` table (BloodHorse lists 2001–2026), plus computed mares-bred and USD stud-fee ranks |
| **Broodmare sire** | Leading Broodmare Sires lists + average sold yearling price (damsire) from the sales index |

Ranking dropdowns only include lists that stallion actually appears on. Years before he entered stud are omitted. **2027 stud fees are hidden.**

- **Leading Sire Rankings** — year, rank, total progeny earnings that year  
- **Stud Fee Rankings** — year, rank, stud fee (USD only; Private / foreign currency unranked)  
- Other BloodHorse lists (first/second/third crop, 2YO, turf, AEI, international regions, etc.) — year and rank  

## Data

All runtime data is in Postgres; the table-by-table map is in
[`docs/RAILWAY.md`](docs/RAILWAY.md#what-lives-where). The folders below are
scraper / loader inputs only (`.dockerignore` keeps them out of the API image):

| Path | Role |
| --- | --- |
| `data/*.csv`, `pedigrees_database.py` | Initial load for the 8 tables and pedigrees (`scripts/load_railway.py`) |
| `Upcoming Sales/`, `Analyzed Sales/` | Sale catalogs and fitted models; publish with `scripts/load_railway.py --only catalogs models` |
| `sales_data/` | Raw Keeneland / Fasig-Tipton catalogs for the pipeline (`sales_lots`) |
| `stallion_rankings_data/`, `live_foal_statistics/` | BloodHorse lists and mares-bred reports for the pipeline |
| `ifha_scraper/ifha_graded_stakes_2003_2026.csv` | IFHA G1–G3 results, worldwide (`graded_stakes`) |

## Pipelines (optional)

**Collection is off.** `crossr_pipeline/collection.py` sets `COLLECTION_ENABLED = False`. The fetch commands below exit without requesting a page. Collected rows stay in the database. LaunchAgents already loaded on the Mac are not stopped by this repo; unload `com.maxsoncook.pq.fetch-gsw` and `com.maxsoncook.pq.fetch-watchdog`, and the pipeline agents listed in [`docs/PIPELINE.md`](docs/PIPELINE.md).

**Pedigrees from Pedigree Query.** The fetch commands are off. Progress already recorded is in `pq_scraper/progress.json` (`last_added`, `last_attempt`, `heartbeat_at`). Misses: `pq_scraper/misses.csv`.

If a horse already has sire/dam names and those parents are in `pedigrees_database.py`, stitch the parent trees in (no network):

```bash
python3 -m pq_scraper.stitch
```

**IFHA graded stakes** (2003–2026): scrapers and checks live under `ifha_scraper/`. Output CSV is `ifha_scraper/ifha_graded_stakes_2003_2026.csv`.

**BloodHorse stallion lists**: yearly CSVs under `stallion_rankings_data/{year}/`. Stud-fee compilation: `stallion_rankings_data/build_stud_fee_database.py`.

**Equibase race records** (headed Chrome; Imperva blocks scripted fetches). Queue is the top-level horses in `pedigrees_database.py`. Results go in `equibase_results.db` at the repo root (year totals and each start). Raw HTML is cached under `equibase_scraper/cache/`. The full pass is long — about two days at the default delay — and resumable: horses already marked ok are skipped. If Chrome shows “Pardon Our Interruption,” finish that page once and rerun the same command.

```bash
python3 -m equibase_scraper.run --enqueue
python3 -m equibase_scraper.run --resume --delay 3
python3 -m equibase_scraper.run --horse "American Pharoah" --year 2012
python3 -m equibase_scraper.run --show "American Pharoah" --year 2012
python3 -m equibase_scraper.run --fill-pedigrees --delay 1
```

## Environment variables

| Variable | Used by | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | API, scripts, pipeline | Postgres connection string (Railway injects it; locally use `crossr_dev`). Required. |
| `CROSSR_FRONTEND_ORIGIN` | API | Comma-separated origins allowed by CORS. |
| `CROSSR_SECURE_COOKIES` | API | `1` in production (HTTPS session cookies). |
| `CROSSR_COMPACT_PEDIGREES` | API | Keep pedigree trees as compact JSON in memory (set automatically by the API). |
| `CROSSR_DB_VERSION_TTL` | API | Seconds between table-version checks (default 15). |
| `CROSSR_SALES_MODEL` | API | `0` falls back to the fee-band price projection. |
| `CROSSR_STAGE` | pipeline | Local staging SQLite for batched scraper writes (default `state/stage.sqlite`). |
| `API_INTERNAL` | web | Where the Next.js server proxies `/api` (Railway: the api service's private domain). |
| `NEXT_PUBLIC_API_URL` | web | Optional absolute API URL for the browser (default: same origin). |

Secrets live only in Railway variables or a local, git-ignored `.env`; nothing is
committed (`.env.example` holds placeholders).

## Data quality and readiness

- `scripts/data_readiness_report.py` (read-only) writes
  [`docs/data-readiness.md`](docs/data-readiness.md): identity duplicates, pedigree
  depth, stud-fee and sales coverage, and for every yearling/weanling lot the share with
  a price, sire, dam, broodmare sire, sire fee at conception, broodmare-sire fee, dam
  production and dam race record, by year. It is the gate before final model training.
- Backfills never overwrite and log every fill in `sales_lots_fill_log`
  (`scripts/backfill_damsire_by_age.py`: damsire from the dam's own record, with her
  age used to separate namesakes).
- `scripts/jockeyclub_mares_bred.py` used to load The Jockey Club's Report of Mares Bred.
  The fetch is off. A saved page passed with `--file` still parses.

## Data sources and access

| Source | How | Notes |
| --- | --- | --- |
| The Jockey Club Report of Mares Bred | `scripts/jockeyclub_mares_bred.py` | fetch is off; a saved `--file` still parses |
| Keeneland catalogs | `scripts/keeneland_catalog.py` | a download is off; a local JSON file still loads |
| Racing Post fee histories | `crossr_pipeline racing-post` | fetch is off |
| BloodHorse ranking lists | CSVs in `stallion_rankings_data/` | the sire-list scrapers are off; saved CSVs stay |
| Equibase race records | `equibase_scraper`, `crossr_pipeline scrape` | fetch is off, including dam and pedigree batches |
| BloodHorse Stallion Register, DRF | **not scraped** | behind bot protection / subscriber content; needs a licensed feed or an export |

## Modeling

- Sales price, Boom % and value models: [`docs/sales-model.md`](docs/sales-model.md),
  results in [`docs/sales-model-results.md`](docs/sales-model-results.md).
- Breeding (expected stallion deal) value, racing value and broodmare value:
  [`docs/breeding-value.md`](docs/breeding-value.md).
- Precomputed hip pages for upcoming sales: [`docs/hip-cache.md`](docs/hip-cache.md).
- Final sale-price training waits for the data-readiness gate above.

## Tests

```bash
python3 -m pytest tests/test_identity.py tests/test_stallion_stats.py tests/test_sire_sales.py   # no database needed
export DATABASE_URL="postgresql://...:.../crossr_dev" && python3 -m pytest tests/e2e -q -rf     # full API, test database only
python3 -m pytest crossr_pipeline equibase_scraper pq_scraper ifha_scraper -q                   # scraper/pipeline units
```

## Known limitations

- Weekly results lists and starred-horse emails run on Monday (docs/weekly-reports.md),
  but the emails need Gmail SMTP settings on Railway, and weekly entries need a permitted
  source loaded with `scripts/import_entries.py`: DRF blocks automated access and
  Equibase entry pages are bot-protected.
- About 15% of yearling/weanling lots still lack a broodmare sire (dams not on file or
  several same-named mares); scraping those dams is in progress.
- Duplicate race-horse rows sharing an Equibase ID were merged on 2026-10-31
  (`scripts/merge_duplicate_race_horses.py`; rows marked `merged`, nothing deleted).
- Many race-horse rows have no foaling year, so some race records don't attach to the
  right horse until Equibase enriches them.
- The local API needs ~1 GB of RAM; on an 8 GB Mac it won't start while the scrapers'
  Chrome is running.

## Layout

```
main.py                 Shared name cleaning / pedigree lookup / inbreeding
hypomating_engine.py    Mating suggestions from GSW crosses
crossr_api/             FastAPI JSON API (:8000)
crossr_core/            Horse profiles, identity/classification, sales queries, auth
web/                    Next.js 14 UI (:3000)
pq_scraper/             Pedigree Query / Wayback importer
ifha_scraper/           IFHA graded-stakes scrape + validation
stallion_rankings_data/ BloodHorse ranking CSVs + fee builders
scripts/                Loaders, backfills, readiness report, pipeline, API helper
crossr_pipeline/        Scheduled scrapers, staging and batched pushes (docs/PIPELINE.md)
tests/                  Unit tests and the end-to-end API suite (tests/e2e)
```

Web routes: `/` home, `/stallions`, `/horses/[name]`, `/hypomating`, `/sales`, `/compare`, `/barn`, `/signin`.

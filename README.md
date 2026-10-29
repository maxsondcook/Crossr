# Crossr

Thoroughbred pedigree, stallion, sales, and mating research. A **Next.js** site (`web/`) on a **FastAPI** JSON API (`crossr_api/`), with all data in Postgres.

The browser only ever gets JSON from the API; raw catalogs and results never leave Postgres.

## What it does

- **Horse profiles** — 5-generation catalog pedigree, female family / produce, race record, stud fee and mares bred, stallion rankings, broodmare-sire history, progeny stats, and proven crosses.
- **Stallion directory** — filter Kentucky and other commercial books by farm, crop, fee, and stud year; compare stallions; star horses into **My Barn**.
- **Hypomating** — given a broodmare, suggest stallions from graded-stakes winner crosses (surface + fee), then offer sons/ancestors when the proven sire is too expensive. Same-cross inbreeding is blocked (for example Citizen Bull is not re-suggested on Into Mischief × Distorted Humor).
- **Sales** — Fasig-Tipton (2004–) and Keeneland (1999–) catalogs: browse a sale, search a sire’s auction record, or look up one horse’s sale history.
- **Accounts** — register / sign in for saved preferences.

Horses are stored as `NAME (YYYY)`. If a search hits two or more foaling years, the app asks which horse you mean.

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

**Pedigrees from Pedigree Query.** Headed Chrome is the primary path (live PQ blocks curl). After graded-stakes horses are in the DB or are real terminal misses, `--queue auto` walks incomplete ancestor slots the same way `pedigrees_cleaner.py` would. Wayback is a polite fallback only and is paused for a few days after an IP block (`pq_scraper/wayback_pause_until.txt`).

```bash
python3 pq_scraper/fetch_pedigrees.py --resume --retry-misses --queue auto --source live --delay 1.5 --save-every 10
```

The live job is a LaunchAgent (`com.maxsoncook.pq.fetch-gsw`) plus a 5-minute heartbeat watchdog (`com.maxsoncook.pq.fetch-watchdog`). Progress: `pq_scraper/progress.json` (`last_added`, `last_attempt`, `heartbeat_at`). Misses: `pq_scraper/misses.csv`. HTTP 0 / connect failures are **not** 404s. Do not raise Wayback concurrency.

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

## Layout

```
main.py                 Shared name cleaning / pedigree lookup / inbreeding
hypomating_engine.py    Mating suggestions from GSW crosses
crossr_api/             FastAPI JSON API (:8000)
crossr_core/            Horse profiles, sales queries, auth
web/                    Next.js 14 UI (:3000)
pq_scraper/             Pedigree Query / Wayback importer
ifha_scraper/           IFHA graded-stakes scrape + validation
stallion_rankings_data/ BloodHorse ranking CSVs + fee builders
scripts/                Data loader (load_railway.py), pipeline, API helper
```

Web routes: `/` home, `/stallions`, `/horses/[name]`, `/hypomating`, `/sales`, `/compare`, `/barn`, `/signin`.

# Running Crossr on Railway

Three services in one Railway project:

| Service | What it is | Built from |
| --- | --- | --- |
| **Postgres** | All Crossr data (see [What lives where](#what-lives-where)) | Railway's Postgres template |
| **api** | FastAPI (`crossr_api`) | `Dockerfile` |
| **web** | Next.js site | `web/Dockerfile` |

Live project: `vigilant-strength` (production).
Site: https://web-production-cbb1f5.up.railway.app · API: https://api-production-f372.up.railway.app/api/health

Build settings live on the services themselves; Railway no longer accepts `railway.json` config files.

Crossr reads and writes **only** Postgres: the API, the training script and the
pipeline all need `DATABASE_URL`, and nothing falls back to local files. The
data files (`data/*.csv`, `pedigrees_database.py`, the sale catalogs, ...) are
inputs to `scripts/load_railway.py` only, and `.dockerignore` keeps them out of
the image.

For local development, point `DATABASE_URL` at the `crossr_dev` database on the
same Railway server (or a copy), never at production `railway`:

```bash
railway run -s Postgres -- sh -c 'echo "postgresql://$PGUSER:$PGPASSWORD@$RAILWAY_TCP_PROXY_DOMAIN:$RAILWAY_TCP_PROXY_PORT/crossr_dev"'
export DATABASE_URL="postgresql://...:.../crossr_dev"
./scripts/run_api.sh
```

## What lives where

| Data | Postgres table(s) | Loaded from (by `scripts/load_railway.py`) |
| --- | --- | --- |
| Stud fees, race horses/seasons/starts, breeding seasons, stallion rankings, graded stakes, sales lots | `stud_fees`, `race_horses`, `race_seasons`, `race_starts`, `breeding_seasons`, `stallion_rankings`, `graded_stakes`, `sales_lots` | `data/<table>.csv`; then kept current by the pipeline |
| Sales hub index (typed copy of `sales_lots`) | `sales_catalogs`, `sales_lot_index` | rebuilt automatically whenever `sales_lots` changes |
| Pedigrees | `pedigrees` | `pedigrees_database.py`; then the scrapers |
| Upcoming and Analyzed sale catalogs | `upcoming_catalogs`, `upcoming_catalog_rows` | `Upcoming Sales/*.csv`, `Analyzed Sales/analyzed_*.csv` (`--only catalogs`) |
| Starred hips and notes on those catalogs | `upcoming_lot_marks` | written by the site; the loader never touches it |
| Expected Market fee-band model, sales price / Boom% model | `crossr_models` (`fee_bands`, `sales_model`) | `Analyzed Sales/expected_market_fee_bands.json`, `Analyzed Sales/sales_model.json.gz` (`--only models`); `scripts/train_sales_model.py` stores a new sales model directly |
| Saved hypothetical matings | `hypofoals` | `hypofoals.py` (`--only hypofoals`) |
| Demo accounts / clients / notes | `industry_roles`, `accounts`, `clients`, `client_preferences`, `notes`, `hypothetical_matings` | `placeholderdatabase/*.csv` (`--only app_state`) |
| Site accounts, sessions, saved barns | `users`, `sessions`, `preferences` | created by the site |
| Change stamps | `crossr_table_versions` | every write bumps it; the API reloads only what changed |

Stakes status (SW ... MG1W) is computed from `race_starts` joined to
`race_horses`, with `graded_stakes` filling in horses and races Equibase lacks
(see `graded_stakes.py`).

To publish a new or updated sale catalog: put the CSV in `Upcoming Sales/` (or
`Analyzed Sales/analyzed_*.csv`) and run `python3 scripts/load_railway.py --only catalogs`.
No deploy is needed.

## 1. Push the repo

```bash
cd ~/Desktop/Crossr
git push -u origin unified        # then open a PR into main, or push to main
```

`data/` and `pedigrees_database.py` are gitignored on purpose: `sales_lots.csv`
is over GitHub's 100 MB limit, and the data belongs in Postgres anyway.

## 2. Create the Railway project

1. railway.com → **New Project** → **Deploy PostgreSQL**.
2. In that project: **+ Create → GitHub Repo → maxsondcook/Crossr**. Rename the
   service to `api`.
   - Settings → Source → branch: `unified` (or `main` after merging).
   - Settings → Build → Dockerfile path: `Dockerfile`; Deploy → healthcheck
     path `/api/health`, timeout 300.
   - Variables → add `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`
     and `CROSSR_FRONTEND_ORIGIN` = `https://<your web domain>` (fill in after step 3).
3. **+ Create → GitHub Repo → maxsondcook/Crossr** again. Rename it to `web`.
   - Settings → Build → Dockerfile path: `web/Dockerfile` (build context stays the repo root).
   - Variables → `API_INTERNAL` = `http://${{api.RAILWAY_PRIVATE_DOMAIN}}:8000`
     and `PORT` = `3000`.
   - Settings → Networking → **Generate Domain** — this is the public site.
4. On `api`, set `PORT` = `8000` (it must match `API_INTERNAL`).

## 3. Load the data (once, from your Mac)

Easiest, with the Railway CLI logged in and this folder linked (`railway link`):

```bash
railway tcp-proxy create -s Postgres --port 5432   # once: public access
railway run -s Postgres -- ./scripts/load_via_railway_cli.sh
```

Or by hand: Railway → Postgres → **Connect** → copy the **public** connection URL.

```bash
cd ~/Desktop/Crossr
python3 -m pip install -r requirements.txt
export DATABASE_URL="postgresql://postgres:...@...proxy.rlwy.net:PORT/railway"
python3 scripts/load_railway.py
```

Takes a few minutes and needs ~5 GB of free RAM for the pedigrees (reading the
51 MB `pedigrees_database.py`); everything else streams. Re-run any time; each
part is swapped in a single transaction. Load one part with `--only sales_lots`
(or `catalogs`, `models`, `hypofoals`, `app_state`, `pedigrees`), skip the
pedigrees with `--skip-pedigrees`, or read the files from another checkout with
`--source ~/Desktop/Crossr`.

Expected counts (Oct 2026 data):

```
stud_fees 15,368   race_horses 318,504   race_seasons 112,276   race_starts 486,583
breeding_seasons 81,868   stallion_rankings 103,957   graded_stakes 90,518
sales_lots 399,590   pedigrees 39,213
```

## 4. Check it

`https://<api domain>/api/health` should return `"backend": "postgres"` and
`"sales_index": true`.

## Scrapers

With `DATABASE_URL` exported, the pipeline (`scripts/pipeline/run.py`) and the
pedigree scrapers write straight to Railway. The running API notices changes
within ~15 s (`crossr_table_versions`) and reloads only the table that changed.

The scheduled pipeline (Equibase race records, sale-parent pedigrees, sales
CSV import) is in [PIPELINE.md](PIPELINE.md).

## Known limits

- Several horse/stallion lookups still load whole tables into memory on first
  use (`race_horses`, `stud_fees`, `breeding_seasons`, `stallion_rankings`,
  `graded_stakes`). The sales hub, auction history and stallion ranking history
  now query Postgres directly instead of holding in-memory copies.

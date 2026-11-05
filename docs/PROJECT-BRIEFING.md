# Crossr: project briefing for a new AI agent

Last updated 2026-11-05 (late). Read this first, then `README.md`, then `bugs/latest.md` (tonight's bug list). This file says what Crossr is, how it runs, what is
done, what is decided, what is open, and the rules every agent working on it follows.

---

## 1. What Crossr is

A thoroughbred breeding and sales analytics site for the owner (Maxson Cook). It has five parts:

- **Stallion directory and profiles:** stud fee, farm, mares bred, rankings, progeny, broodmare-sire crosses,
  stallion sales analytics.
- **Horse profiles** for any horse: pedigree, race record, female family, breeding suggestions.
- **Hypomating:** pick a mare and a stallion and get a projected foal, similar crosses, and suggested and
  alternative stallions.
- **Sales hub:** past sale results, and upcoming catalogs (Keeneland November 2026, Eastern Fall 2026). Each hip
  page has its pedigree, crosses, auction history and a market projection. There are client filters, markup tools
  and notes.
- **Accounts:** starred horses ("My Barn") and weekly racing emails.

The goal is a fast, accurate site, with comprehensive horse and sales data and a validated sale-price model. The
owner wants it ready to show to employers, and the next phase is mostly data collection and accuracy.

## 2. Where things live

| Thing | Where |
|---|---|
| Repo | `~/Desktop/Crossr`, GitHub `maxsondcook/Crossr`. Working branch **`unified`**. `main` was brought level with `unified` on 2026-10-31. |
| Live web | https://web-production-cbb1f5.up.railway.app (Next.js 14, `web/`) |
| Live API | https://api-production-f372.up.railway.app (FastAPI, `crossr_api/app.py`) |
| Database | Railway Postgres, project `vigilant-strength`, services `Postgres`, `api`, `web`. Production DB `railway`; test DB `crossr_dev` (a full copy of the big tables since 2026-10-31, about 946 MB). |
| Railway CLI | `~/.local/railway-cli/node_modules/.bin/railway`, logged in. The folder is linked. |
| Scheduled jobs | macOS launchd, run from a **separate checkout `~/Crossr-pipeline`** (code in `crossr_pipeline/launchd.py`). |
| Railway budget | **$20/month hard limit.** The site goes down at the limit. Keep writes batched and the DB small. |

Every push to `unified` redeploys the live api and web, so pushing is a release.

### Code map
- `crossr_core/`: business logic.
  - `horses.py`: profiles and the stallion roster.
  - `identity.py`: namesake-safe horse identity and classification.
  - `sales.py`: sire sales analytics.
  - `breeding_value.py`: colt deal value and broodmare value.
  - `sales_model.py` / `projections.py`: price projection.
  - `weekly.py`: weekly reports and emails.
  - `stallion_status.py`: dead or pensioned status corrections and registry scope.
  - `pedigree_fill.py`: fills pedigree gaps from ancestors' records.
  - `upcoming.py`: upcoming catalogs.
  - `hip_cache.py`: precomputed hip pages.
- `crossr_api/app.py`: every API route.
- `web/`: the Next.js frontend.
  - `web/app/horses/[name]/page.js`: the profile page.
  - `web/app/sales/page.js`: the sales hub.
- `crossr_pipeline/`: the scraping and loading pipeline (`python -m crossr_pipeline ...`).
  - `scrape.py`: the Equibase batches.
  - `launchd.py`: the job definitions.
- `equibase_scraper/`, `pq_scraper/`, `ifha_scraper/`: the scraper internals.
- `scripts/`: one-off and scheduled tools.
  - `data_audit.py`: nightly accuracy audit.
  - `stallion_status.py` and `stallion_news_watch.py`: deaths and pensions.
  - `import_entries.py`: race entries.
  - `jockeyclub_mares_bred.py`, `keeneland_catalog.py`, `merge_duplicate_race_horses.py`,
    `backfill_damsire_by_age.py`, `data_readiness_report.py`, `train_sales_model.py`.
- `tests/`: unit tests. Run `DATABASE_URL= python3 -m pytest -q tests --ignore=tests/e2e crossr_pipeline equibase_scraper ifha_scraper`.
  On 2026-11-05: 491 passed, 37 skipped.
- `tests/nightly/`: **the nightly bug hunt** (`python -m tests.nightly`, section 5a).
- `docs/`: design docs (listed in section 9). `docs/handover/` has copies of the other agents' plans.

### Main tables (Postgres)

| Table | Rows (approx.) | Holds |
|---|---|---|
| `sales_lots` | 405k | Sale lots from about 1999 to 2026 |
| `race_horses` | 326k | Equibase profiles (a `merged` status marks duplicates folded into another row) |
| `race_starts` | 922k | Starts |
| `race_seasons` | 230k | Season and career totals |
| `pedigrees` | 77k | JSON trees |
| `stud_fees` | 25k | Fees by stallion and year, with farm and notes |
| `breeding_seasons` | 83k | Jockey Club Report of Mares Bred |
| `stallion_rankings` | — | BloodHorse sire lists |
| `graded_stakes` | — | Graded stakes |
| `upcoming_catalogs` | — | Upcoming sale catalogs |
| `race_entries` | — | Race entries |
| `weekly_reports` | — | Weekly entries and results lists |
| `stallion_status_overrides` | — | Status corrections |
| `stallion_status_suggestions` | — | News matches awaiting review |
| `data_audit_runs` | — | Audit results |
| `users`, `preferences` | — | Accounts |

After a bulk write, bump `crossr_table_versions` with `railway_db._bump(conn, table, rows)` so the API reloads.

## 3. Rules the owner set (follow all of them)

1. **Never fabricate data.** A blank or "—" beats a guess.
2. **Never confuse horses that share a name.** Match on name plus foaling year (and sire where it helps). With no
   year, match only when one horse has that name. Englishman (2002 stallion) vs Englishman (2023 colt) is the
   standing example. Prefer showing nothing over showing a namesake's data.
3. **Respect each site's terms, robots.txt and rate limits.** Never bypass paywalls, logins, captchas or bot
   protection: no spoofed browsers, no Incapsula or DataDome evasion.
   - Blocked, so not scraped: BloodHorse (Incapsula), DRF (403, and its terms ban scrapers), Paulick Report
     (DataDome), Horse Racing Nation, Racing Australia, Japan's NAR.
   - **Equibase:** its terms of use prohibit "any robot, spider, scraper or any other automated means". The
     existing Equibase scraper predates this finding. The owner has been told and **the decision is pending**
     (see section 7).
4. **Keep secrets out of git.** Credentials go in Railway variables or env vars, never in code or chat.
5. **Nothing destructive without safeguards.** Back up the rows first (to `db-backups/`, which is gitignored),
   mark rows instead of deleting where possible, log every fill, and keep an undo path.
6. **Ask before pushing** to `unified` (it deploys live), unless the owner already said to push.
7. **No final model training until the owner says go.** The data must be complete first.
8. **No future information in model features.** Use only what was known at the time of the sale.
9. The registry is North America only for now, with a one-setting switch to worldwide (section 5). European
   data is kept, never deleted.
10. Plain-language reports to the owner: lead with the outcome, define jargon, no acronyms without explanation.

## 4. How agents work here (conventions)

- Several agents (Claude Code sessions) work in parallel on `unified`. **Pull before you start, keep commits
  small, and don't push other agents' unpushed work.** The pattern used:
  ```bash
  git commit ...; C=$(git rev-parse HEAD); git fetch origin unified
  git worktree add --detach /tmp/wt origin/unified && (cd /tmp/wt && git cherry-pick $C && git push origin HEAD:unified)
  git worktree remove --force /tmp/wt; git merge origin/unified
  ```
- After a push, wait for the Railway deploy (`railway deployment list -s api`) and check the live site.
- **Running against the DB locally:** wrap commands with the Railway CLI. `scripts/pipeline/railway_env.sh railway <cmd>`
  builds `DATABASE_URL` for production; use `crossr_dev` for the test DB.
- The Mac has only 8 GB of RAM. Don't run the API locally while scrapers run; verify on the live site instead.
- **Only one Chrome scraper at a time** on the Mac (`logs/pipeline/chrome.lock`).
- `~/Crossr-pipeline` is the scraping agent's checkout, often on its own branch with unpushed work. Don't
  reset it or merge into it.
- Installing or loading launchd jobs is done **by the owner** in their own terminal (agents are blocked from
  persistent system changes).

## 5. What is done

### Infrastructure and deploy
- Runs purely on Railway Postgres (no CSV or JSON stores).
- Dockerfiles run as non-root with health checks.
- README and `.env.example` are current.
- **Cost cuts:** batched pipeline writes, `crossr_dev` kept small (currently a full copy for model work; shrink it
  back after final training), Racing Post weekly.
- `main` is synced with `unified`. Old Cursor PRs maxsondcook/Crossr#1, #3 and #4 are stale and should be
  closed, not merged.

### Identity and data quality
- `crossr_core/identity.py`:
  - classifies each horse as stallion, broodmare, racing female, racing male, gelding or unknown;
  - classifies stallions as active, inactive, pensioned, deceased or historical;
  - checks that a stud card belongs to the right horse (sex, foaling year, sire, first season);
  - `stands_in_north_america` (a Japanese or European farm is not North America even with a dollar fee).
- **Duplicate Equibase records merged (2026-10-31):**
  - 1,170 rows marked `merged`, none deleted;
  - duplicate starts and seasons removed;
  - backed up in `db-backups/`;
  - 0 duplicate Equibase IDs remain.
- **Sale lots cleaned:**
  - 5,200 empty Fasig-Tipton 2004 placeholder rows and 7 exact duplicates removed, backed up first;
  - 59,445 blank broodmare sires filled by dam age (`scripts/backfill_damsire_by_age.py`, logged in
    `sales_lots_fill_log`).
- **Stallion directory parents** must match the stallion's foaling year (fixed a namesake bug: Oscar Performance
  was listed by Cyrano de Bergerac).
- **Top-progeny earnings** come from each horse's race record. They used to add up stakes purses: Magnitude showed
  $14.6M against a real $9.63M.
- **Pedigree charts** fill short branches from ancestors' own records (`pedigree_fill.py`).
- **Hip numbers** match regardless of zero-padding ("35" = "0035").
- **Nightly data audit:** `scripts/data_audit.py` runs read-only checks on the database and the live pages:
  - earnings vs race record;
  - impossible seasons;
  - duplicates and hipless lots;
  - fee jumps;
  - "N/A" labels;
  - repeated grades;
  - pedigree gaps;
  - empty panels;
  - pages that fail to load.

  It writes to `logs/audit/` and `data_audit_runs`.

### Stallion registry
- **The registry** is every stallion on a current stud card (this or last season), plus every stallion the Jockey
  Club reports bred to mares in 2026, minus pensioned, retired, dead or exported.
- **Scope:** `CROSSR_STALLION_SCOPE` on the Railway api service is `north_america` (the default, about 862
  stallions) or `world` (about 1,147). Hypomating suggestions stay North America-only regardless.
- **Status corrections:** `stallion_status_overrides` wins over the stud card, because stud cards always say
  active.
  - Recorded so far: Wootton Bassett and Frosted (deceased), War Front (pensioned).
  - Tool: `scripts/stallion_status.py set|list|suggestions|approve|reject`.
- **News watch:** `scripts/stallion_news_watch.py` reads Thoroughbred Daily News, which robots.txt allows
  (10-second crawl delay).
  - It flags headlines about deaths, pensionings, exports and relocations.
  - `--archive --since 2018` scans the yearly sitemaps (56k headlines) without opening articles.
  - Nothing changes until the owner approves a flag.
- **Profiles** show "Pensioned" or "Deceased", and hide "Select for hypomating" for those stallions.
- **2026 stud cards:** 218 stallions that bred in 2026 have no card (no fee or farm):
  `state/shared/bred-2026-without-stud-card.csv`.

### Features (master prompt phases)
- **Profiles:**
  - profile-type heroes;
  - breeding panel: suggested stallions for females, similar stallions for males;
  - best broodmare-sire crosses table (expands to the horses);
  - sales-by-cross;
  - stallion sales analytics panel (periods, chart, per-sale lots);
  - female family;
  - tabs layout.
- **Breeding values:** `crossr_core/breeding_value.py` (docs: `docs/breeding-value.md`):
  - **colt deal value:** sons' initial fee × 400 ÷ colts of racing age; young sires are valued from comparables
    within ±10% fee;
  - **broodmare value** and **racing value**.
- **Weekly reports (Phase 7):** `crossr_core/weekly.py`, `docs/weekly-reports.md`.
  - Every Monday it builds the entries and results lists and emails opted-in users about their starred horses:
    - the horse itself;
    - progeny of a starred broodmare or stallion;
    - progeny of a starred broodmare sire's daughters.
  - Duplicate emails are prevented and failed sends are retried.
  - Entries come from the NYRA daily adapter, which is built but not yet run on production.
  - Emails need Gmail SMTP credentials (section 7).
- **Sales hub:**
  - Keeneland November 2026 catalog (3,406 hips, with book, session and covering sire);
  - filters (sold as, session, book, sire, sex…);
  - client setup with per-client filters;
  - markup (pencil, highlighter, eraser, undo and redo);
  - notes with voice typing;
  - tabs;
  - "Horse (Sire x Dam by Damsire)" header.
- **Sale-price model (Phases 12–14, preliminary only):** on branch `claude/sales-model-3255a3`; pipeline pushed.
  See `docs/price-model.md` and `docs/price-model-preliminary.md`.
  - Ridge and LightGBM both reach test R² 0.57, against 0.39 for the best baseline.
  - 80% price ranges come from conformalized quantile regression (CQR), with 80.9% coverage on test years.
  - Not used by the site yet.

### 5a. Nightly bug hunt and speed tooling (2026-11-05)
- **`python -m tests.nightly`** (run with `scripts/pipeline/railway_env.sh railway` for the database checks)
  runs three sets of checks:
  - **Unit tests.**
  - **The data audit's database checks.**
  - **Live checks of the site:**
    - the registry (pensioned or dead stallions not listed);
    - the identity rules (Curlin is a stallion, Zenyatta a broodmare, Englishman ambiguous, War Front
      pensioned, Frosted deceased);
    - random directory stallions' profiles;
    - top-progeny earnings against the race record;
    - grades not repeated;
    - hypomating suggestions and reports;
    - every upcoming catalog's hip list;
    - random hips (pedigree named, zero-padding);
    - sire sales summaries;
    - the weekly endpoints;
    - web pages.

  Each check has a **speed budget** (`tests/nightly/live.py: BUDGETS`).
- **Output:** `bugs/latest.md` (and `bugs/inbox/<date>.md` / `.json`), gitignored. Each bug has an id, a reproduce
  command, expected vs actual, and likely files. **Any agent, Cursor included, can start from this file.**
- **Scheduled agent:** the Claude Desktop scheduled task `crossr-nightly-bug-hunt`, daily at 5:00 am while the
  app is open. It runs the hunt in its own worktree, fixes what it can on branch `nightly-fix/<date>` with tests,
  pushes **only that branch**, and writes `bugs/fixes-<date>.md`. The owner reviews and merges to ship. It never
  deploys, writes to production or scrapes.
- **Step timings:** every `/api` response carries a `Server-Timing` header listing its main steps
  (`crossr_core/timing.py`; the instrumented functions are listed in `crossr_api/app.py`). Use it to profile,
  in the browser's network panel or with `curl -D -`.
- **Speed work done:**
  - **Upcoming catalogs** are parsed once per catalog version (`upcoming._base_lots`). They used to be re-read on
    every hip request.
  - **Career earnings** are an in-memory table per race-table version.
  - **The active-stallion list** is cached.
  - **Startup warms** the dam-produce index, earnings, parents, progeny, active stallions and catalogs.
  - **Results:**

    | Request | Before | After |
    |---|---|---|
    | Saved hip | 0.7–0.9 s | 0.03 s |
    | Hip list | 1.7 s | 0.5 s |
    | Hypomating report | 2.4 s | 1.0 s |
    | Suggestions | 1–1.8 s | 0.5 s |
    | Profiles | — | about 0.25 s |
- **Still to speed up:**
  - **A hip opened for the first time** takes 2–7 s. It needs the precompute job loaded
    (`com.crossr.pipeline.precompute`), or a faster `sale_workspace`.
  - **The hypomating report** (about 1 s) is mostly `similar_cross_rows`, `similar_active_stallions` (pedigree
    similarity against every active stallion) and `_nick_auctions`.
  - **The stallion list** takes about 0.7 s with a 218 KB payload; consider trimming fields and paging.
  - **The first request after a deploy** is slow until the warm-up finishes.

## 6. Current numbers (2026-11-04/05)
- **Broodmare sire on yearling and weanling lots:** 85% overall, 89–93% for 2010–2023.
- **Sire stud fee at conception:** 85–93%.
- **Dam production record:** 70–80%.
- **Dam scraping** (dams of lots missing a broodmare sire): 5,275 of 21,932 searched by 2026-11-04 (4,256
  matched); still running.
- **Speed:**
  - pages: about 0.1 s;
  - profiles: 0.3–0.4 s;
  - a saved hip: 0.1–0.4 s;
  - a hip opened for the first time: 2–8 s (the fix is the nightly precompute job, which needs loading).

## 7. Open decisions waiting on the owner
**Status 2026-11-05:** the owner is working on getting **fully licensed, complete data** and asked everyone to
hold. Later the same day: all scrapers stay off. Automated collection is disabled in
`crossr_pipeline/collection.py` (`COLLECTION_ENABLED = False`). A push to this repo does not unload jobs
already running from `~/Crossr-pipeline`; those plist names are in `docs/PIPELINE.md`.

1. **Equibase terms.** Their terms forbid automated scraping, and race records and pedigrees depend on it.
   The options:
   - keep scraping at a polite pace (5 s between pages);
   - license data from Equibase or The Jockey Club Information Systems;
   - stop.

   The weekly refresh, the backfill and results all hang on this.
2. **NYRA entries on production:** the race-entries agent has the adapter tested on `crossr_dev` and asks to run
   it on production and load its daily job.
3. **The Racing API** (paid, about £25–60 a month; UK and Ireland racecards and results): sign up? If yes, the
   key goes in an env var.
4. **Gmail SMTP for the weekly emails:** set `CROSSR_SMTP_USER` and `CROSSR_SMTP_PASSWORD` (an app password) on the
   Railway api service.
5. **Load launchd jobs** (owner runs them):
   ```bash
   cd ~/Crossr-pipeline && .venv/bin/python -m crossr_pipeline install-launchd
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.crossr.pipeline.audit.plist
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.crossr.pipeline.precompute.plist
   # stallion-news stays unloaded. Collection is off. See docs/PIPELINE.md.
   ```
6. **Stallion status updates from the news scan:** 8 stallions still listed as active
   ([section 8](#8-what-is-left-in-priority-order), item 2).
7. **Stud cards for the 218:** use state breeders' association rosters? (robots.txt and terms checked per site.)

## 8. What is left, in priority order
0. **Nightly bugs:** start each work session from `bugs/latest.md` and any `nightly-fix/*` branch waiting for
   review. Open on 2026-11-05:
   - Run Tiger Run is in the directory, but his profile returns 404;
   - the stallion list is over its 0.5 s budget.
1. **Data collection** (the owner's main focus; **on hold pending licensing**). The plan is `docs/handover/data-priorities-plan-2026-11-04.md`.
   - **Weekly refresh** of every horse that raced in 2026 or is entered: built, on the pipeline branch.
   - **Pedigrees** for the 172 directory stallions with no tree (Cupid, Unified, Oscar Performance…), queued.
     Without them, half of every hip pedigree by those sires is blank.
   - **The dam backlog** (above).
   - **Race records** for horses sold since 2015: about 182k sold since 2010, only 22.7k have a record. This is the
     biggest gap for the model.
   - **About 51k never-tried sale parents' pedigrees.**
   - **Timing:** about 3–4 weeks of round-the-clock scraping, or about 3 months at the recent pace. Keeping the Mac
     awake and plugged in matters most.
2. **Accuracy:**
   - Fix the audit's open findings: grades repeated in race names ("Iroquois Stakes (Gr. 3) G3"), and "N/A"
     height and accomplishments in the API.
   - Review the news-scan candidates. **Still listed but reported dead:** Dominus (July 2026), Early Voting
     (October 2026), Girvin (August 2026), Outflanker, Seeking the Soul, The Big Beast. **Reported pensioned:**
     Daaher, Mineshaft. Acclamation is a namesake: the Irish horse died, the American one is active.
   - Tighten the news matcher's false positives ("California Chrome co-owner dies", "Hall of Fame rider…").
3. **Stallion rankings:** the owner keeps BloodHorse. They save the year-end sire lists by hand each year, and an
   importer is being built by the scraping agent.
4. **Final model training:** only after the owner's go-ahead, once the data is complete. Then put the model on
   the hip pages, and shrink `crossr_dev` back.
5. **Speed:** load the precompute job; profile the slow first-hip compute.
6. **Polish:**
   - the hydration warning on the "Go Back" label;
   - per-year charts on the rankings page;
   - uppercase styling consistency.

## 9. Key docs
- `README.md`: setup, run and deploy, data sources, known limitations.
- `docs/RAILWAY.md`, `docs/PIPELINE.md`: database and pipeline operations.
- `docs/data-readiness.md` (`scripts/data_readiness_report.py`): the model's readiness gate. The proposed criteria
  for eligible lots:
  - price ≥ 60%;
  - sire, dam and broodmare sire ≥ 98%;
  - fee at conception ≥ 85%;
  - dam production ≥ 70%;
  - dam race record ≥ 60%;
  - 0 duplicate Equibase IDs.
- `docs/sales-model.md`, `docs/price-model.md`, `docs/price-model-preliminary.md`, `docs/breeding-value.md`.
- `docs/weekly-reports.md`, `docs/hip-cache.md`.
- `docs/handover/`: the scraping plan, the entries-source survey, and the duplicate-merge write-up.

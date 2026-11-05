# race_horses duplicate refnos (2026-10-31)

Branch `claude/dedupe-race-horses-refno`, commit 62d19c5, on local `unified` 798b7a9 (which is ahead of origin/unified). Not pushed.

## Cause
build_catalog_queue keys yearless catalog horses as `NAME | SIRE | DAM`, so one horse gets a queue row per catalog spelling (plus bare / dated / `[dam by X]` sale-parent rows). Every row was fetched and `_store_resolved` saved the profile on its own row. All 2,047 duplicate rows on prod are status ok.

## Fix (equibase_scraper/run.py)
- `_store_resolved`: if the profile's refno is already on another ok row, save into that row and mark the queue row `merged` (detail `merged into race_horses <id>`, profile + children cleared, pedigree_key kept so it is not re-queued).
- `fetch_horse`: search match whose refno is stored (same or unknown year) -> merged without loading the profile.
- `follow_merged` used by run_fetch and crossr_pipeline/scrape.process_item.
- Works on all three backends (db.py, pgdb, stage) via save_profile.

## Merge script: scripts/merge_duplicate_race_horses.py
Dry-run on production (read-only): 877 refnos / 2,047 rows; 1,170 rows merged; 541 records moved to the kept id; 23,040 race_starts + 4,944 race_seasons deleted; 119 crossr_pipeline_queue details repointed; 0 conflicts.
Full plan: race-horses-merge-plan-production.csv; output: race-horses-merge-dryrun-production.txt (this folder).
prod totals before: race_starts 944,827, race_seasons 235,442, race_horses 326,481.

## Not done
- `--apply` on crossr_dev was blocked by the permission classifier (shared DB); the apply SQL is untested. Run on crossr_dev first, then prod with the user's OK.
- Before applying to prod: push or discard the local stage (state/stage.sqlite), or dirty rows pushed later restore the copies.

## Applied 2026-10-31 (user approved, run in the user's terminal)
- crossr_dev: 410 rows merged, 0 duplicate refnos left. Backup db-backups/race_horses-merge-crossr_dev-2026-10-31T130546.jsonl.gz
- production: 1,170 rows merged, 0 duplicate refnos left; race_starts 944,827 -> 921,787, race_seasons 235,442 -> 230,498 (exactly the dry run). Backup db-backups/race_horses-merge-railway-2026-10-31T130621.jsonl.gz
- Checks: no starts on merged rows, every merged row points at an ok row with a profile, no queue detail left on a merged row. Table versions bumped 18:06 UTC.
- Code fix (62d19c5) still not merged/pushed: until it runs, the pipeline can add new copies.

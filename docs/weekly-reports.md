# Weekly entries, results and starred-horse emails (Phase 7)

Code: `crossr_core/weekly.py` · entries import: `scripts/import_entries.py` · tests: `tests/test_weekly.py`

## What runs on Monday

`python -m crossr_core.weekly run` (launchd `com.crossr.pipeline.weekly`, Monday 08:00, and again at wake if the Mac slept):

1. **Entries list** for this week, Monday through Sunday (Monday's own races included), from `race_entries`. Stored in `weekly_reports` (kind `entries`).
2. **Results list** for last week, Monday through Sunday, from `race_starts`. Stored in `weekly_reports` (kind `results`).
3. **One email per subscribed user.** It has up to four sections, and only sections with something in them are sent:
   - starred horses;
   - starred broodmares' progeny;
   - starred stallions' progeny (active, pensioned or dead: only the pedigree link matters);
   - starred broodmare sires' daughters' progeny (broodmare sire → daughter → foal).

Each race date falls in exactly one week, so a race is never on two weekly lists. `GET /api/weekly/entries` and `GET /api/weekly/results` (`?week=YYYY-MM-DD`) return the stored lists.

## Emails

- **Opt-in:** a user turns the email on in their barn ("Weekly email report"), and chooses entries, results or both. It is off by default. No email is sent in a week with nothing to report.
- **No repeats:** every emailed item is logged in `weekly_notified` (user, entry/result, race). An entry and its later result are each sent once.
- **Late results:** the scraper refreshes active horses weekly, so a start can reach the database days after the race. Results look back 28 days (`CROSSR_RESULTS_LOOKBACK_DAYS`) and skip what was already sent, so late results go out the following week.
- **Retries:**
  - Temporary SMTP failures (connection drops, 4xx replies) are retried 3 times with backoff.
  - Permanent ones (such as bad credentials) are not retried.
  - A failed email stays `failed` in `weekly_emails` and is retried on the next run.
- **Re-running is safe:** a second run in the same week skips users already `sent`. A missed Monday is recovered by running the job later in the week, or with `--date YYYY-MM-DD`.
- **Locking:** one run at a time (Postgres advisory lock). Each run is logged in `crossr_pipeline_runs` (job `weekly-reports`).

Matching starred horses to runners:
- Progeny are matched by Equibase refno.
- They are matched by name only when the starred name is one horse: every dated record agrees on a single foaling year. Undated rows are unscraped placeholders.
- A runner foaled less than three years after the starred horse is never its progeny.
- To pin a namesake, star it with its year, for example `Englishman (2002)`.

## Setup needed

Add these to the **api** service's variables on Railway. The Monday job reads them through `railway run -s api`:

| Variable | Value |
|---|---|
| `CROSSR_SMTP_USER` | the Gmail address that sends the reports |
| `CROSSR_SMTP_PASSWORD` | a Gmail **app password** for it (Google Account → Security → App passwords) |
| `CROSSR_EMAIL_FROM` | optional, defaults to `CROSSR_SMTP_USER` |
| `CROSSR_SITE_URL` | optional, defaults to the production web URL (used for profile links) |

Without credentials, the job still builds and stores the lists. It marks each due email `skipped` and sends it on the first run after credentials are added.

Install the Monday schedule with the other pipeline agents (`python -m crossr_pipeline install-launchd`, then load `com.crossr.pipeline.weekly`).

## Entries source

- **Daily Racing Form:** answers automated requests, including `robots.txt`, with 403. It is not scraped.
- **Equibase:** its entries pages sit behind bot protection, which we do not get around.

Entries therefore come in through `scripts/import_entries.py` from a CSV the project is allowed to use. That could be:
- a licensed feed export (Equibase or DRF data licensing);
- a track's published overnight;
- entries typed in by hand.

The importer:
- links each horse by refno, or by a name that is unique;
- keeps unmatched horses' entries (so a missing pedigree never holds up a list) and re-links them on later imports;
- updates re-imported races in place.

Until a source is chosen, weekly emails carry results only.

## Active-horse refresh

The existing `races-refresh` step of the hourly scrape job (`crossr_pipeline/scrape.py`) re-opens the Equibase profile of every horse with a start in the last 60 days, at most once every 7 days. That update brings in the horse's new starts, which are what the results list and emails are built from. Horses with an imported entry but no recent start are not refreshed yet.

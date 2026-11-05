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

**NYRA entries are off.** `python -m crossr_pipeline entries` exits without fetching, and `install-launchd` does not write `com.crossr.pipeline.entries`. If that agent is already loaded from `~/Crossr-pipeline`, unload `com.crossr.pipeline.entries.plist` on the Mac. The Monday email job still builds lists from rows already stored.
- nyra.com has no robots.txt rules and its Terms & Conditions have no clause against automated reading.
- We read it politely: plain HTTP with an honest User-Agent, one small per-race page at a time, 5 s apart (about 40 requests, 3–4 minutes a day). Any 403/429 stops the run for the day; nothing is retried harder or worked around.
- Cards are drawn 3–4 days ahead, so the daily run adds new cards as they post. After each run, this week's stored entries list (`weekly_reports`) is refreshed. Emails still go out on Monday only.
- Every runner carries its Equibase refno, so horses are linked by identity. A runner that drops off a re-read race is marked `scratched`.

**Other sources, checked 2026-11-04:**

| Source | Status |
|---|---|
| Equibase entries pages | Terms of Use forbid any robot, spider or scraper and any republishing without written consent. Also behind Imperva bot protection. Not used. |
| Daily Racing Form | Subscriber Agreement forbids automated access "for any purpose" without written permission, and limits data to personal, non-commercial use. Not used. The permitted route is a written licence (DRF Data Services). |
| Equibase data licensing | Official feeds (entries, charts). Quote only. |
| The Racing API | North America add-on is closed to new subscribers. |
| Goalserve | Lists "USA: racing": $200/month, $1,500/year, free trial. US thoroughbred coverage unverified. |
| Apify / parse.bot "Equibase scrapers" | Use residential proxies to get past Equibase's bot wall. Rejected. |

Other tracks can still come in through `scripts/import_entries.py`, from a CSV the project is allowed to use. Both paths write through `crossr_core/entries.py`.

**Linking runners to horses:**
- Each runner is linked by Equibase refno.
- Failing that, by name, only when exactly one horse has that name. When the entry gives a foal year, that horse must also be a dated record with the same year: an undated placeholder may be an older namesake.
- A namesake with a different refno is never linked.

Unlinked runners keep their entry and are listed in the view `race_entries_unlinked` (refno, name, foal year). The Equibase pipeline uses that view to scrape them. Every later run re-links them once the horse exists.

**Undo:**
- `DELETE FROM race_entries WHERE source = 'nyra'` removes everything the adapter wrote.
- The added columns (`first_seen_at`, `foal_year`) and the view are additive.

## Active-horse refresh

The `races-refresh` step of the hourly scrape job (`crossr_pipeline/scrape.py`) is off with the rest of collection. It used to re-open the Equibase profile of every horse with a start in the last 60 days, at most once every 7 days. That update brings in the horse's new starts, which are what the results list and emails are built from. Entered horses (`race_entries`) and horses that raced in 2026 should also be refreshed, so their results land within the week. That change is with the data-pipeline chat (see below).

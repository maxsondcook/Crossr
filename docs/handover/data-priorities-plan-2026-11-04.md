# Data priorities: what's done, what's proposed (2026-11-04)

The code is on branch claude/data-pipeline-6a41a2 (e2c4e1d) and in ~/Crossr-pipeline. It is not pushed to unified.

## 1. Weekly refresh of horses active in 2026: done
- **Which horses:** races-refresh now takes every ok horse with a start since Jan 1 (or the last 60 days in January and February) or a row in race_entries.
- **Spacing and change detection:** unchanged. A horse is skipped if it was fetched in the last 6 days.
- **Size:** 1,125 horses have a 2026 start. race_entries is empty for now, so entries add none. Today 711 are due.
- **Time:** one profile load each, about 450 per 45-minute batch, so a weekly pass is 2–3 batches (about 2.5 hours of scraping).

## 2. Yearly stallion rankings: no job exists. Proposal below.
- **Where the data comes from now:** stallion_rankings is built from BloodHorse sire-list CSVs (stallion_rankings_data/<year>/, from bloodhorse_sirelists/scrape_sirelists.py). BloodHorse is now blocked by Incapsula.
- **What's loaded:** 2001–2026, with 13 lists per year. The 2026 lists are a mid-year snapshot from about Oct 23.
- **Proposal:** a yearly launchd job in mid-January (after the year-end lists are final) that refreshes the closed year's lists from Equibase's leader pages (equibase.com/stats, leading sires by year). It would use the same Chrome profile and chrome.lock as the scrape, at the same pace, about 13 pages.
- **Caveat:** Equibase's columns differ from BloodHorse's. It has starters, winners, stakes winners and earnings, but no stud fee, farm or AEI. Those columns would stay blank or come from stud_fees.
- **Fallback:** a manual step where the user saves the BloodHorse year-end CSVs into stallion_rankings_data/<year>/ and the importer runs.
- **Needs a decision before building.**

## 3. 2026 stallion pedigrees: queued
- **New step:** pedigrees-stallions runs in each batch after catalogs and the refresh, before the dam list. Its list is the 731 stallions from breeding_seasons 2026, most mares bred first.
- **Matching:** each is searched as a sire (thoroughbred, entire, foaled 1996–2023).
- **Shared states:** it shares queue states with pedigrees-sales, so stallions already marked ambiguous or not found are skipped.
- **Size:** 172 stallions have no tree and 208 are incomplete. That's about 1–2 batches.
- **Risk:** common names (Authentic, Annapolis, Nashville) may come back ambiguous and are not guessed.

## 4. Stud cards (218 stallions bred in 2026 with no fee or farm): mostly not on Racing Post
- **Racing Post coverage:** the weekly job has already tried them:
  - 122 have no fees there (for example Gulfport, Newgrange, Shaaz, Red Run, Wit);
  - 63 don't match any Racing Post horse;
  - 10 are ambiguous;
  - 2 are errors (Kingsbarns and Dornoch: "fee-history page has no __NEXT_DATA__");
  - 21 were never queued.
- **Who they are:** mostly regional stallions (PR 19, LA 18, CA 17, KY 13, NM 11, OK 11, FL 10, AR 9).
- **Proposal:** add the 21 to the Racing Post queue and retry the 2 errors. For the rest, use state breeders' association stallion rosters (FTBOA, CTBA, LTBA, TTA, OTBA, NYTB, Puerto Rico), each fetched only after checking that its robots.txt allows it and its terms are fine. That's one roster page per state, once a year.
- **Not started.**

## 5. Back-data backfill plan (not started; for approval)

**What's missing:**
- **Sale parents:** 87,657 (5,180 sires, 82,477 dams). The queue has tried 36,498: 25,103 complete, 8,210 incomplete (retried after 30 days), 1,465 ambiguous, 961 not found, 686 errors. About 51k have never been tried, mostly dams.
- **race_horses:** 213,425 are pending (queued, never fetched), against 71,778 ok.
- **Race records of sold horses:** of 182k distinct sale-lot names since 2010, only 22.7k have an ok race record. The rest are the biggest gap for the sales model ("did the yearling become a runner?").

**Proposed order:**
1. the dam list, which is running (~16.6k dams left);
2. 2026 stallions;
3. the weekly 2026 refresh;
4. race records of horses sold since 2015, newest sale first;
5. the remaining pending race_horses;
6. sale-parent trees not yet tried;
7. retries of incomplete trees.

**Throughput:** about 450 page loads per 45-minute batch, about one batch an hour, so up to about 10k pages a day only if the Mac stays awake and plugged in 24 hours. With sleep and block pages, expect 3–6k a day. At that rate, items 4–5 are roughly 30–60 days of scraping.

**Railway cost:**
- **Writes:** pushes are one small transaction a day, and egress is small because the Mac no longer re-reads tables.
- **Storage:** race_starts is about 13 rows per ok horse, so +150k horses is about +2M starts, roughly +1 GB of Postgres. The volume is 2.6 GB now, and volume cost is negligible.
- **API memory:** this is the cost to watch. The API loads race tables into memory when they change, so its RAM grows with them. That needs a check once race_starts passes about 2M rows.

**Blockers:** none in code. The scrape launchd agent is currently not loaded (see below).

## Scrape agent not loaded
- **What happened:** com.crossr.pipeline.scrape is missing from launchctl since about 18:33 on Nov 4. The last batch ended normally at its 45-minute deadline (exit 75), so it was unloaded afterwards. The cause is unknown, and com.crossr.stallion-registry is not loaded either. I did not reload it; that's waiting on the user.
- **Dam progress so far:** 5,275 of 21,932 dams searched (4,256 found, 837 ambiguous, 182 not found). 19,825 lots filled so far (sales_lots_fill_log, source damsire-scraped-dam, Oct 31 – Nov 4).

## 4b. Global stud cards: sources checked (robots.txt, 2026-11-05)

| Source | Covers | robots.txt | Proposal |
| --- | --- | --- | --- |
| Racing Post (stallion pages, fee history) | GB/IRE/FR, plus many US, JPN and AUS stallions | allows (only /bloodstock/sales/ and UGC are disallowed) | Already in use, weekly. Extend the queue from the NA lists to every roster stallion (1,147). The stallion-book index page answers 406 to plain HTTP, so it goes through the Chrome job as today. |
| JBIS (jbis.or.jp) | Japan: every stallion standing, with fee and farm. Covers American Pharoah, California Chrome and others. | allows, apart from /premium, /csv and a few others; **Crawl-delay: 600** (10 minutes) | Yearly job at one page per 10 minutes. About 250 stallions is roughly 2 days, once a year (after the Japanese fee announcements in Oct–Dec). The stallion index URL needs finding: /seri/stallion/ returned 404. |
| aushorse.com.au | Australia: stallion directory | allows; Crawl-delay: 10 | Yearly job, ~10 s per page. |
| Racing Australia / Australian Stud Book | Australia: official | **Disallow: /** for all bots (studbook.org.au has no robots.txt) | Do not scrape. |
| NZTBA (nzthoroughbred.co.nz) | New Zealand | allows, except admin/users/tools | Yearly job. |
| Weatherbys | GB stud book | robots.txt has no rules | The stallion data sits behind their portal or is paid, so probably not usable. Check their terms first. |
| stallionbook.co.uk | GB/IRE stallion book | **disallow: /** | Do not scrape. |
| France Galop / IFCE | France | allow public pages | IFCE (haras nationaux) publishes the annual French stallion list; check the format. |
| Tattersalls / Arqana | Sales companies, not stud cards | allow | Not needed. |
| TBA South Africa / ITBA Ireland | | robots.txt did not answer | Check by hand later. |
| The Jockey Club (US) | Mares bred | allows; Crawl-delay: 120 | Already weekly. |
| US state breeder rosters | Regional US stallions (the 218) | check each site | Per item 4. |

Order: Racing Post for every roster stallion, then JBIS, aushorse, NZTBA, IFCE, then the US state rosters. Each is a separate yearly job, run outside the Equibase batches. The Chrome-based ones share chrome.lock.

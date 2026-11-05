# Race entries source survey (entries chat, 2026-11-04)

| Source | Coverage | Cost | Terms / access | Verdict |
|---|---|---|---|---|
| Equibase site (entries pages) | All N. America | free | ToU forbid any robot/spider/scraper and republication without written consent; Imperva bot wall | NOT usable |
| Equibase data licensing (feeds: entries, charts, PPs) | All N. America, official | quote only (no public price) | written licence | best official option; needs user to contact Equibase |
| Equibase Virtual Stable | only horses you add; email alerts for early/final entries + results | free | personal, non-commercial use | only for personal alerts, not a site feed |
| DRF | all | n/a | 403 to automated requests | NOT usable |
| The Racing API, NA add-on | USA+Canada results (116k); racecards unclear | n/a | NA add-on "currently unavailable to new subscribers" | not available |
| Goalserve horse racing feed | lists "USA: racing", entries+results+odds, XML/JSON | $200/mo, $900/6mo, $1,500/yr; free trial | commercial licence | candidate; verify US thoroughbred coverage via trial |
| Apify/parse.bot Equibase scrapers | Equibase | ~$6/1k | use residential proxies to beat Imperva = anti-bot evasion | REJECTED |
| HorseRacingNation entries | all | free | robots blocks AI bots; /terms 403 | not usable |
| NYRA (nyra.com/<track>/racing/entries) | Aqueduct/Belmont/Saratoga only, server-rendered HTML, posted 3-4 days ahead | free | no robots.txt (404), Terms page has no scraping/reuse clause | usable, polite rate |
| Santa Anita / 1/ST | stakes PDFs on ctfassets; entries via JS | free | ToU not located | not yet |
| Churchill/Keeneland/Woodbine | robots permissive; pages JS/Equibase-embedded | free | per-track ToU check needed | later |

Lead time: entries are drawn 2-4 days out (NYRA: "typically posted 3-4 days before"), so a Monday run sees Mon-Thu at most. Full-week coverage needs a daily entries pull + midweek list refresh, regardless of source.

# Stallion rankings (BloodHorse sire lists)

`stallion_rankings` holds BloodHorse's leading-sire lists, 2001 onward. BloodHorse is behind bot protection, so the pipeline doesn't fetch it: once a year you save the pages from your own browser and a script loads them.

## When

The lists are final in early **January**. Save them then, for the year that just ended (for example, January 2027 for the 2026 lists). You can also save a mid-year snapshot; loading the same list again replaces the earlier copy.

## Which pages

Open the sire-list archive at <https://www.bloodhorse.com/horse-racing/thoroughbred-breeding/sire-lists/archive>. Pick the year, then save each of these 13 lists. The archive's own list names are in brackets.

| List (archive `seoName`) | Region | Loads as |
| --- | --- | --- |
| General (`general`) | North America | Leading Sire Rankings |
| First-Crop (`first-crop`) | North America | Leading First Crop Sires |
| Second-Crop (`second-crop`) | North America | Leading Second-Crop Sires |
| Third-Crop (`third-crop`) | North America | Leading Third-Crop Sires |
| Two-Year-Old (`two-year-old`) | North America | Leading Two-Year-Old Sires |
| Turf (`turf`) | North America | Leading Turf Sires |
| Lifetime AEI (`lifetime-aei`) | North America | Leading Sires by AEI |
| Broodmare (`broodmare`) | North America | Leading Broodmare Sires |
| International (`international`) | International | summary, North America, Europe & Dubai, Japan & Hong Kong |
| International First-Crop (`international-first-crop`) | International | the same four tables |
| International Second-Crop (`international-second-crop`) | International | the same four tables |
| International Third-Crop (`international-third-crop`) | International | the same four tables |
| International Two-Year-Old (`international-two-year-old`) | International | the same four tables |

North American lists use "All Regions". Each international page carries all four tables, so save it once.

## How to save

1. Open the list, wait until the whole table has loaded, and scroll to the bottom. If the page shows "Show more", load all of it first.
2. Use **File > Save Page As…** with the format **"Webpage, HTML Only"** (Chrome) or **"Page Source"** (Safari).
3. Put the file in `stallion_rankings_data/saved/<year>/`, for example `stallion_rankings_data/saved/2026/`.

You don't need to rename anything: Chrome and Safari write the page's address into the file, and the script reads the list and year from it. If a file isn't recognised, rename it like `2026_general.html` or `2026_international-first-crop.html`.

## Load

```bash
.venv/bin/python scripts/import_bloodhorse_saved.py --year 2026            # dry run: what would load
```

Check that every list shows the right year and a sensible stallion count and leader. Then run against production:

```bash
scripts/pipeline/railway_env.sh railway .venv/bin/python scripts/import_bloodhorse_saved.py --year 2026 --apply
```

`--apply` does four things:

- writes each list as `stallion_rankings_data/<year>/<year>StallionRankings - <list>.csv`, the same files earlier years use;
- backs up the rows it replaces to `db-backups/stallion_rankings_<time>.csv`;
- replaces only those lists in `stallion_rankings`;
- bumps the table version, so the API reloads.

The script skips a page that's a bot check or sign-in wall and says so. Re-save that page and run again.

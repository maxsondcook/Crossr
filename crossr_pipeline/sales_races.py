"""Queue: race records of horses sold at auction, newest sale first.

Every named lot since FIRST_SALE_YEAR whose horse has no race record yet is
looked up on Equibase by name, foal year, sire and dam (one search, usually
one profile). Horses foaled in the last two years are skipped: most have not
raced, and the weekly races-refresh picks them up once they have a record.
"""

from __future__ import annotations

from datetime import datetime, timezone

from equibase_scraper.queue import clean_name

JOB = "races-sales"
QUEUE_BATCH = "sales-races"
FIRST_SALE_YEAR = 2015
MIN_AGE = 3  # foaled at least this many years ago
DONE = {"ok", "not_found", "ambiguous", "year_mismatch", "merged"}


def load_items(conn, now: datetime | None = None) -> list[dict]:
    """One item per (name, foal year) of a named lot, most recent sale first."""
    last_foal = (now or datetime.now(timezone.utc)).year - MIN_AGE
    rows = conn.execute(
        """
        SELECT MAX(btrim(name)) AS name, birth_year, MAX(sire) AS sire, MAX(dam) AS dam,
               MAX(catalog_year) AS latest
        FROM sales_lots
        WHERE COALESCE(btrim(name), '') <> '' AND birth_year ~ '^[0-9]{4}$' AND birth_year::int <= %s
          AND catalog_year ~ '^[0-9]{4}$' AND catalog_year::int >= %s
        GROUP BY upper(btrim(name)), birth_year
        """,
        (last_foal, FIRST_SALE_YEAR),
    ).fetchall()
    items = []
    for row in rows:
        name_key = clean_name(row["name"])
        if not name_key:
            continue
        items.append({"name": row["name"], "name_key": name_key, "foal_year": row["birth_year"],
                      "sire": row["sire"] or "", "dam": row["dam"] or "", "latest": row["latest"],
                      "key": f"{name_key}:{row['birth_year']}"})
    items.sort(key=lambda it: (it["latest"], it["name_key"]), reverse=True)
    return items


def build_queue(items: list[dict], states: dict, known: set[tuple[str, str]], limit: int | None = None) -> list[dict]:
    """Items without a final race_horses row (``known``: (name_key, foal_year))
    and not finished in the queue."""
    todo = []
    for item in items:
        if (item["name_key"], item["foal_year"]) in known:
            continue
        if (states.get(item["key"]) or {}).get("status") in DONE:
            continue
        todo.append(item)
        if limit and len(todo) >= limit:
            break
    return todo

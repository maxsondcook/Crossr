"""Keeneland online-catalog export, and filling an upcoming catalog from it.

Keeneland's catalog table (…/sales/<year>/<id>/<sale>/catalog-table/) can show
Book, Session, Color, Dam Sire, DOB and State Foaled; its "Export with current
filters" CSV keeps the columns switched on. ``export_catalog`` drives that in a
plain Playwright Chrome (no stealth), and ``enrich_catalog`` merges the export
into an upcoming catalog by hip, filling only blank cells:

    SESSION, BOOK (added after SESSION), COLOR, SIRE OF DAM, YEAR OF BIRTH
    (MM/DD/YYYY, the FT layout), FOALED, COVERING SIRE, PREGNANT, SOLD AS DESCRIPTION

It writes the merged rows to Postgres (upcoming_catalog_rows) and, when given,
back to the CSV in Upcoming Sales/ so a later ``load_railway.py --only
catalogs`` keeps them.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

COLUMN_SWITCHES = [
    "field_book", "field_session", "field_sex", "field_foaling_area", "field_sold_as", "field_color",
    "field_sire", "field_dam", "field_broodmare_sire", "field_breeding_status", "field_covering_sire",
    "field_consignor", "field_foaling_date", "field_barn_text", "field_out", "field_hip_number",
]

# Keeneland color words -> the abbreviations the FT catalogs use.
COLORS = {
    "BAY": "B", "DARK BAY/BROWN": "DK B/", "CHESTNUT": "CH", "GRAY/ROAN": "GR/RO",
    "GRAY": "GR", "ROAN": "RO", "BLACK": "BLK", "WHITE": "WH",
}

# catalog column <- export column
FILL = {
    "SESSION": "Session",
    "BOOK": "Book",
    "COLOR": "Color",
    "SIRE OF DAM": "Dam Sire",
    "YEAR OF BIRTH": "DOB",
    "FOALED": "State Foaled",
    "COVERING SIRE": "Cover",
    "PREGNANT": "Pregnant",
    "SOLD AS DESCRIPTION": "Sold As",
}


def export_catalog(url: str, dest: Path, profile_dir: Path) -> Path:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(profile_dir), channel="chrome", headless=False, accept_downloads=True,
            viewport={"width": 1400, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            columns = page.get_by_role("button", name=re.compile(r"^\s*Columns\s*$", re.I)).first
            columns.wait_for(timeout=90000)
            page.wait_for_timeout(4000)
            columns.click()
            page.wait_for_timeout(1500)
            for name in COLUMN_SWITCHES:
                box = page.locator(f"input[type=checkbox][name='{name}']").first
                if box.count() and not box.is_checked():
                    box.evaluate("e => e.click()")
                    page.wait_for_timeout(300)
            page.keyboard.press("Escape")
            page.wait_for_timeout(1500)
            page.get_by_role("button", name=re.compile(r"^\s*Export\s*$", re.I)).first.click()
            page.wait_for_timeout(1500)
            with page.expect_download(timeout=120000) as info:
                page.get_by_role("button", name=re.compile(r"Export to \.CSV", re.I)).first.click()
            dest.parent.mkdir(parents=True, exist_ok=True)
            info.value.save_as(str(dest))
        finally:
            ctx.close()
    return dest


def hip_key(value) -> str:
    text = str(value or "").strip()
    return text.lstrip("0") or text


def read_export(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {hip_key(row.get("Hip Number")): row for row in csv.DictReader(handle)}


def export_value(column: str, row: dict) -> str:
    raw = (row.get(FILL[column]) or "").strip()
    if column == "COLOR":
        return COLORS.get(raw.upper(), raw)
    return raw


def merge_rows(columns: list[str], rows: list[dict], export: dict[str, dict]) -> tuple[list[str], list[dict], dict]:
    """Fill blank cells from the export. Returns (columns, rows, filled counts)."""
    columns = list(columns)
    if "BOOK" not in columns:
        at = columns.index("SESSION") + 1 if "SESSION" in columns else len(columns)
        columns.insert(at, "BOOK")
    filled = {column: 0 for column in FILL}
    out = []
    for row in rows:
        row = dict(row)
        source = export.get(hip_key(row.get("HIP")))
        for column in FILL:
            row.setdefault(column, "")
            if source and not str(row.get(column) or "").strip():
                value = export_value(column, source)
                if value:
                    row[column] = value
                    filled[column] += 1
        out.append(row)
    return columns, out, filled


def enrich_catalog(conn, catalog_id: str, export_path: Path, csv_path: Path | None = None) -> dict:
    from psycopg.types.json import Jsonb

    record = conn.execute("SELECT columns FROM upcoming_catalogs WHERE id = %s", (catalog_id,)).fetchone()
    if not record:
        raise SystemExit(f"No upcoming catalog {catalog_id!r}")
    rows = [r["data"] for r in conn.execute(
        "SELECT data FROM upcoming_catalog_rows WHERE catalog_id = %s ORDER BY row_no", (catalog_id,)
    )]
    columns, merged, filled = merge_rows(record["columns"], rows, read_export(export_path))
    with conn.transaction():
        conn.execute("UPDATE upcoming_catalogs SET columns = %s, updated_at = now() WHERE id = %s",
                     (Jsonb(columns), catalog_id))
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE upcoming_catalog_rows SET data = %s WHERE catalog_id = %s AND row_no = %s",
                [(Jsonb(row), catalog_id, i) for i, row in enumerate(merged)],
            )
    from equibase_scraper import pgdb

    pgdb.flush_versions(conn, ("upcoming_catalogs",))
    if csv_path is not None:
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
            writer.writeheader()
            writer.writerows(merged)
    return filled

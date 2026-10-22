"""Load upcoming sale catalogs from the Upcoming Sales/ folder.

The sales hub lists every CSV in that folder. Drop a catalog file there and it
appears on the next request — no rebuild required. Analyzed Sales/ is not used
as the primary source.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UPCOMING_DIR = ROOT / "Upcoming Sales"

HIP_KEYS = ("HIP", "HIP NUMBER", "HIP NO", "HIP #", "LOT", "HIP NO.")
NAME_KEYS = ("HORSE NAME", "NAME", "HORSE", "HORSE_NAME")
SIRE_KEYS = ("SIRE",)
DAM_KEYS = ("DAM",)
BMS_KEYS = ("SIRE OF DAM", "BMS", "BROODMARE SIRE", "DAM SIRE")
SEX_KEYS = ("SEX",)
COLOR_KEYS = ("COLOR", "COLOUR")
YOB_KEYS = ("YEAR OF BIRTH", "YOB", "DOB", "YEAR OF BIRTH / AGE", "FOALING YEAR")
FOALED_KEYS = ("FOALED", "STATE", "STATE FOALED", "BRED")
SOLD_AS_KEYS = ("SOLD AS", "SOLD AS DESCRIPTION", "DESCRIPTION")
COVER_KEYS = ("COVERING SIRE",)
CONSIGNOR_KEYS = ("CONSIGNOR", "PROPERTY LINE", "PROPERTYLINE1", "CONSIGNED BY")
NOTES_KEYS = ("NOTES",)
CROSS_KEYS = ("CROSS SUCCESS",)
DAM_RACER_KEYS = ("DAM SUCCESS (RACER)", "DAM SUCCESS RACER")
DAM_PROD_KEYS = ("DAM SUCCESS (PRODUCER)", "DAM SUCCESS PRODUCER")
RACING_KEYS = ("RACING SUCCESS",)
STAR_KEYS = ("STARRED", "STAR")
BARN_KEYS = ("BARN", "BARN #", "BARN NUMBER")


def _norm_header(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\ufeff", "").strip().upper())


def _pick(row: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        if key in row and str(row.get(key) or "").strip():
            return str(row.get(key) or "").strip()
    return ""


def _sale_year_from_name(filename: str) -> str:
    match = re.search(r"\b(20\d{2}|19\d{2})\b", filename)
    return match.group(1) if match else ""


def _sale_title_from_name(filename: str) -> str:
    stem = re.sub(r"\.csv$", "", filename, flags=re.IGNORECASE)
    stem = re.sub(r"^analyzed_", "", stem, flags=re.IGNORECASE)
    stem = stem.replace("_", " ").replace("-", " ")
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem or filename


def _company_from_name(filename: str) -> str:
    lower = filename.lower()
    if "fasig" in lower:
        return "Fasig-Tipton"
    if "keeneland" in lower:
        return "Keeneland"
    return ""


def _hip_text(raw: str) -> str:
    text = (raw or "").strip()
    digits = re.sub(r"\D", "", text)
    if digits:
        try:
            return str(int(digits))
        except ValueError:
            return text
    return text


def list_catalog_files() -> list[dict]:
    """Every CSV in Upcoming Sales/, newest-looking names last alphabetically."""
    if not UPCOMING_DIR.is_dir():
        return []
    catalogs = []
    for path in sorted(UPCOMING_DIR.glob("*.csv")):
        catalogs.append({
            "sale_title": _sale_title_from_name(path.name),
            "sale_year": _sale_year_from_name(path.name) or "2026",
            "sale_company": _company_from_name(path.name),
            "sale_kind": "upcoming",
            "source_file": str(path.relative_to(ROOT)),
            "filename": path.name,
            "hip_count": None,
        })
    return catalogs


def load_catalog_rows(filename: str = "", source_file: str = "") -> list[dict]:
    """Parse one Upcoming Sales CSV into catalog_hips-shaped rows."""
    path = None
    if source_file:
        candidate = ROOT / source_file
        if candidate.is_file() and UPCOMING_DIR.resolve() in candidate.resolve().parents:
            path = candidate
        elif candidate.is_file() and candidate.parent.resolve() == UPCOMING_DIR.resolve():
            path = candidate
    if path is None and filename:
        path = UPCOMING_DIR / Path(filename).name
    if path is None or not path.is_file():
        return []

    sale_title = _sale_title_from_name(path.name)
    sale_year = _sale_year_from_name(path.name) or "2026"
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return []
        field_map = {_norm_header(name): name for name in reader.fieldnames if name is not None}

        def mapped(raw_row: dict) -> dict:
            return {_norm_header(key): (value or "") for key, value in raw_row.items() if key is not None}

        for index, raw in enumerate(reader, 1):
            row = mapped(raw)
            hip = _hip_text(_pick(row, HIP_KEYS))
            if not hip:
                continue
            birth = _pick(row, YOB_KEYS)
            year_match = re.search(r"\d{4}", birth)
            horse_name = _pick(row, NAME_KEYS)
            sire = _pick(row, SIRE_KEYS)
            dam = _pick(row, DAM_KEYS)
            if not horse_name or re.match(r"^hip\s*\d+$", horse_name, re.I):
                yr = (year_match.group(0)[2:] if year_match else "00")
                if sire or dam:
                    horse_name = f"{sire} x {dam} '{yr}".strip()
                else:
                    horse_name = f"Hip {hip}"
            rows.append({
                "hip_id": str(index),
                "sale_title": sale_title,
                "sale_year": sale_year,
                "hip": hip,
                "horse_name": horse_name,
                "sex": _pick(row, SEX_KEYS)[:1].upper(),
                "color": _pick(row, COLOR_KEYS),
                "sire": sire,
                "dam": dam,
                "sire_of_dam": _pick(row, BMS_KEYS),
                "year_of_birth": year_match.group(0) if year_match else birth,
                "foaled": _pick(row, FOALED_KEYS).upper(),
                "sold_as": _pick(row, SOLD_AS_KEYS),
                "covering_sire": _pick(row, COVER_KEYS),
                "consignor": _pick(row, CONSIGNOR_KEYS),
                "barn": _pick(row, BARN_KEYS),
                "notes": _pick(row, NOTES_KEYS),
                "cross_success": _pick(row, CROSS_KEYS),
                "dam_success_racer": _pick(row, DAM_RACER_KEYS),
                "dam_success_producer": _pick(row, DAM_PROD_KEYS),
                "racing_success": _pick(row, RACING_KEYS),
                "starred": _pick(row, STAR_KEYS),
                "source_file": str(path.relative_to(ROOT)),
                "filename": path.name,
            })
    return rows


def catalog_summary() -> list[dict]:
    summaries = []
    for entry in list_catalog_files():
        hips = load_catalog_rows(filename=entry["filename"])
        entry = dict(entry)
        entry["hip_count"] = len(hips)
        summaries.append(entry)
    return summaries


def find_hip(filename: str, hip: str, sale_year: str = "") -> dict | None:
    rows = load_catalog_rows(filename=filename)
    target = _hip_text(hip)
    for row in rows:
        if sale_year and str(row.get("sale_year")) != str(sale_year):
            continue
        if _hip_text(row.get("hip") or "") == target:
            return row
    return None

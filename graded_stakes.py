"""Race wins from the ``graded_stakes`` table in Postgres (crossr_core.sample_db).

Despite the name, the table holds every race result we have, not just graded
stakes: IFHA graded/group stakes plus hand-entered wins (allowance, maiden,
claiming, ...) for horses without an Equibase profile.

Race type lives in the ``Group`` / ``Grade`` column:
- black type: G1, G2, G3 (also "Grade 1", "Group 2", "Gr3"), Listed / L, Stakes;
- anything else (Allowance, Optional Claiming, Maiden, Claiming, blank) is a
  win that is shown in race lists but never counts as a stakes win.

Normalization
-------------
- ``Race Year`` is derived from ``Date (ISO)`` (``YYYY-MM-DD``), then a year in
  ``Date`` (``27 September 2025``), then an existing ``Race Year`` value.
- ``Grade`` is an alias of ``Group`` so older callers keep working.
- Literal ``N/A`` strings are treated as missing; cells are stripped strings.
- Rows with Horse Name ``N/A`` / blank are dropped (races with no result).

Default ``winners_only=True`` keeps ``Place == 1`` only (every current feature
is winner-oriented). Pass ``winners_only=False`` for all finishers.
"""

from __future__ import annotations

import re
import threading

from crossr_core import sample_db

MISSING_NAMES = {"", "N/A", "NAN", "NONE", "<NA>"}

_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_GRADE_RE = re.compile(r"^(?:G|GR|GRADE|GROUP)\s*\.?\s*([123])\b")
_LISTED = {"L", "LR", "LISTED", "LISTED RACE", "STAKES", "STK", "BLACK TYPE", "BT"}

_lock = threading.Lock()
_cache: dict[bool, tuple[float, list[dict]]] = {}


def graded_level(grade) -> int | None:
    """1/2/3 for a graded or group race, else None."""
    match = _GRADE_RE.match(str(grade or "").strip().upper())
    return int(match.group(1)) if match else None


def is_black_type(grade) -> bool:
    """True for G1-G3, Listed and (ungraded) Stakes races; False for allowance etc."""
    text = str(grade or "").strip().upper()
    if not text:
        return False
    return graded_level(text) is not None or text in _LISTED


def _clean(value) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.upper() in {"N/A", "NAN", "NONE", "<NA>"} else text


def _int_or_blank(value):
    text = _clean(value)
    if not text:
        return ""
    try:
        return int(round(float(text)))
    except ValueError:
        return ""


def _race_year(row: dict):
    iso = _clean(row.get("Date (ISO)"))
    if len(iso) >= 4 and iso[:4].isdigit():
        return int(iso[:4])
    match = _YEAR_RE.search(_clean(row.get("Date")))
    if match:
        return int(match.group(1))
    return _int_or_blank(row.get("Race Year"))


def _normalize(row) -> dict | None:
    rec = {col: _clean(row.get(col)) for col in sample_db.TABLES["graded_stakes"]}
    if rec["Horse Name"].upper() in MISSING_NAMES:
        return None
    rec["Race Year"] = _race_year(rec)
    rec["Grade"] = rec["Group"] or rec["Grade"]
    rec["Place"] = _int_or_blank(rec["Place"])
    year = _int_or_blank(rec["Foaling Year"])
    rec["Foaling Year"] = str(year) if year != "" else ""
    return rec


def load_stakes_records(path=None, winners_only=True):
    """List-of-dicts form used by hypomating, the sale tools and the API.

    ``path`` is accepted for old callers and ignored: data comes from Postgres.
    Reloads when the table version changes.
    """
    version = sample_db.table_version("graded_stakes")
    key = bool(winners_only)
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] == version:
            return hit[1]
    records = []
    for row in sample_db.load_table("graded_stakes"):
        rec = _normalize(row)
        if rec is None:
            continue
        if winners_only and rec["Place"] != 1:
            continue
        records.append(rec)
    with _lock:
        _cache[key] = (version, records)
    return records


def load_stakes_data(path=None, winners_only=True):
    """Backward-compatible name: Place==1 winners."""
    return load_stakes_records(path=path, winners_only=winners_only)

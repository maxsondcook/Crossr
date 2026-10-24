"""Single entry point for the pedigree map.

Railway Postgres (pedigrees table) when DATABASE_URL is set, otherwise the local
pedigrees_database.py module. Callers get the same {key: tree} dict either way.
"""

from __future__ import annotations

import importlib
import sys
import threading

_lock = threading.RLock()
_cache: dict | None = None
_cache_version: float | None = None


def _pg():
    from crossr_core import railway_db

    return railway_db if railway_db.enabled() else None


def _from_module(refresh: bool) -> dict:
    import pedigrees_database  # 49 MB module, imported lazily

    if refresh and "pedigrees_database" in sys.modules:
        pedigrees_database = importlib.reload(sys.modules["pedigrees_database"])
    data = getattr(pedigrees_database, "pedigree_map", {})
    return data if isinstance(data, dict) else {}


def get_pedigree_map(refresh: bool = False) -> dict:
    """Return the shared pedigree map (treat as read-only; copy before mutating)."""
    global _cache, _cache_version
    pg = _pg()
    with _lock:
        if pg is None:
            if _cache is None or refresh:
                _cache = _from_module(refresh)
            return _cache
        version = pg.table_version("pedigrees", max_age=0 if refresh else None)
        if _cache is None or refresh or version != _cache_version:
            _cache = pg.read_pedigree_map()
            _cache_version = version
        return _cache


def sync_to_railway(items: dict) -> int:
    """Upsert trees into Railway when it is configured; no-op locally."""
    pg = _pg()
    if pg is None or not items:
        return 0
    return pg.upsert_pedigrees(items)

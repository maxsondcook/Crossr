"""Crossr FastAPI application."""
import os
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import main
import hypomating_engine
from crossr_core import horses as horse_svc
from crossr_core import sales as sales_svc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

app = FastAPI(title="Crossr", version="1.0.0")

_frontend = os.environ.get("CROSSR_FRONTEND_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_frontend, "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_PROFILES = None
_rate_lock = Lock()
_rate_hits = defaultdict(deque)
RATE_LIMITS = {
    "/api/search": (30, 60),
    "/api/hypomating/suggest": (8, 60),
    "/api/hypomating/report": (12, 60),
}


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    for prefix, (max_hits, window) in RATE_LIMITS.items():
        if path.startswith(prefix):
            ip = _client_ip(request)
            key = f"{ip}:{prefix}"
            now = time.time()
            with _rate_lock:
                bucket = _rate_hits[key]
                while bucket and now - bucket[0] > window:
                    bucket.popleft()
                if len(bucket) >= max_hits:
                    raise HTTPException(status_code=429, detail="Too many requests. Please wait a moment.")
                bucket.append(now)
            break
    return await call_next(request)


@app.on_event("startup")
def startup():
    global _PROFILES
    _PROFILES = main.load_master_profiles()
    horse_svc.build_search_index(_PROFILES)


def profiles():
    return _PROFILES if _PROFILES is not None else main.load_master_profiles()


class SuggestBody(BaseModel):
    mare: str
    surface: str = "neither"
    max_fee: Optional[int] = None


class ReportBody(BaseModel):
    sire: str
    dam: str


@app.get("/api/health")
def health():
    db_ok = os.path.exists(sales_svc.db_path())
    return {"ok": True, "sales_index": db_ok, "horses": len(main.PEDIGREE_DATABASE)}


@app.get("/api/search")
def search(q: str = Query("", min_length=1), limit: int = Query(15, ge=1, le=40)):
    return {"results": horse_svc.search_horses(q, limit=limit, profiles=profiles())}


@app.get("/api/horses/{name}")
def horse_profile(name: str):
    payload = horse_svc.get_horse_profile(name, profiles=profiles())
    if not payload:
        raise HTTPException(status_code=404, detail="Horse not found")
    return payload


@app.post("/api/hypomating/suggest")
def hypomating_suggest(body: SuggestBody):
    result = hypomating_engine.suggest_matings(
        main.PEDIGREE_DATABASE,
        profiles(),
        body.mare,
        surface_pref=body.surface,
        max_fee=body.max_fee,
    )
    if result.get("error") == "not_found":
        raise HTTPException(
            status_code=404,
            detail="That broodmare is not in the Crossr pedigree database yet.",
        )
    return result


@app.get("/api/hypomating/lineage/{stallion}")
def hypomating_lineage(stallion: str, max_fee: Optional[int] = None):
    return hypomating_engine.lineage_options_payload(stallion, profiles(), budget_filter=max_fee)


@app.post("/api/hypomating/report")
def hypomating_report(body: ReportBody):
    result = hypomating_engine.build_hypo_report(
        main.PEDIGREE_DATABASE,
        profiles(),
        body.sire,
        body.dam,
        persist=False,
    )
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Broodmare not found")
    result["pedigree"] = horse_svc.trim_pedigree(result["pedigree"])
    return result


@app.get("/api/sales/years")
def sales_years():
    return {"years": sales_svc.list_years()}


@app.get("/api/sales/catalogs")
def sales_catalogs(year: Optional[int] = None):
    return {"catalogs": sales_svc.list_catalogs(year=year)}


@app.get("/api/sales/lots")
def sales_lots(
    catalog_id: int,
    sort: str = "price_desc",
    sex: Optional[str] = None,
    limit: int = Query(80, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return sales_svc.catalog_lots(catalog_id, sort=sort, sex=sex, limit=limit, offset=offset)


@app.get("/api/sales/sire/{name}")
def sales_sire(
    name: str,
    sort: str = "year_desc",
    sex: Optional[str] = None,
    limit: int = Query(80, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return sales_svc.sire_lots(name, sort=sort, sex=sex, limit=limit, offset=offset)


@app.get("/api/sales/horse")
def sales_horse(
    name: str = "",
    year: str = "",
    sire: str = "",
    dam: str = "",
    sort: str = "year_desc",
    limit: int = Query(80, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    if name and (not sire or not dam):
        profile = horse_svc.get_horse_profile(name, profiles=profiles())
        if profile and profile.get("pedigree"):
            tree = profile["pedigree"]
            if not sire and tree.get("sire"):
                sire = tree["sire"]["name"]
            if not dam and tree.get("dam"):
                dam = tree["dam"]["name"]
            if not year and profile.get("year"):
                year = str(profile["year"])
    return sales_svc.horse_lots(name=name, year=year, sire=sire, dam=dam, sort=sort, limit=limit, offset=offset)

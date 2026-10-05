"""Crossr FastAPI — JSON only. Never serves sales_data/ or stakes CSVs."""
import os
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Optional

from fastapi import Cookie, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import main
import hypomating_engine
from crossr_core import horses as horse_svc
from crossr_core import sales as sales_svc
from crossr_core import auth as auth_svc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

app = FastAPI(title="Crossr", version="1.0.0", docs_url=None, redoc_url=None)

_frontend = os.environ.get("CROSSR_FRONTEND_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get("CROSSR_FRONTEND_ORIGIN", "http://localhost:3000,http://127.0.0.1:3000").split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

_PROFILES = None
_rate_lock = Lock()
_rate_hits = defaultdict(deque)
RATE_LIMITS = {
    "/api/search": (30, 60),
    "/api/stallions": (40, 60),
    "/api/hypomating/suggest": (8, 60),
    "/api/hypomating/report": (12, 60),
    "/api/auth/register": (8, 60),
    "/api/auth/login": (12, 60),
}

BLOCKED_PATH_BITS = (
    "sales_data",
    "graded_stakes_winners",
    "live_foal_statistics",
    ".csv",
    ".db",
    "pedigrees_database",
    "stallion_profiles",
)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def protect_and_rate_limit(request: Request, call_next):
    path = request.url.path.lower()
    if any(bit in path for bit in BLOCKED_PATH_BITS):
        return JSONResponse({"detail": "Not found"}, status_code=404)

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
                    return JSONResponse({"detail": "Too many requests. Please wait a moment."}, status_code=429)
                bucket.append(now)
            break
    return await call_next(request)


@app.on_event("startup")
def startup():
    global _PROFILES
    _PROFILES = main.load_master_profiles()
    horse_svc.build_search_index(_PROFILES)
    auth_svc.init_db()


def profiles():
    return _PROFILES if _PROFILES is not None else main.load_master_profiles()


class SuggestBody(BaseModel):
    mare: str
    surface: str = "neither"
    min_fee: Optional[int] = None
    max_fee: Optional[int] = None


class ReportBody(BaseModel):
    sire: str
    dam: str


class RegisterBody(BaseModel):
    email: str
    username: str
    password: str
    preferences: Optional[dict] = None


class LoginBody(BaseModel):
    identifier: str
    password: str
    preferences: Optional[dict] = None


class PreferencesBody(BaseModel):
    starred: Optional[list] = None
    hypofoals: Optional[list] = None
    favorites: Optional[list] = None
    analyzed: Optional[list] = None


COOKIE_NAME = "crossr_session"


def _set_session(response: Response, token: str):
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=os.environ.get("CROSSR_SECURE_COOKIES") == "1",
        max_age=30 * 86400,
        path="/",
    )


def _clear_session(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")


@app.get("/api/health")
def health():
    return {"ok": True, "sales_index": os.path.exists(sales_svc.db_path())}


@app.post("/api/auth/register")
def auth_register(body: RegisterBody, response: Response):
    result, err = auth_svc.create_user(body.email, body.username, body.password, body.preferences)
    if err:
        raise HTTPException(status_code=400, detail=err)
    _set_session(response, result["token"])
    return {"user": result["user"], "preferences": result["preferences"]}


@app.post("/api/auth/login")
def auth_login(body: LoginBody, response: Response):
    result, err = auth_svc.login(body.identifier, body.password, body.preferences)
    if err:
        raise HTTPException(status_code=401, detail=err)
    _set_session(response, result["token"])
    return {"user": result["user"], "preferences": result["preferences"]}


@app.post("/api/auth/logout")
def auth_logout(response: Response, crossr_session: Optional[str] = Cookie(None)):
    auth_svc.logout(crossr_session)
    _clear_session(response)
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(crossr_session: Optional[str] = Cookie(None)):
    user = auth_svc.user_from_session(crossr_session)
    if not user:
        return {"user": None, "preferences": None}
    return {"user": user, "preferences": auth_svc.get_preferences(user["id"])}


@app.post("/api/auth/preferences")
def auth_preferences(body: PreferencesBody, crossr_session: Optional[str] = Cookie(None)):
    user = auth_svc.user_from_session(crossr_session)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    prefs = auth_svc.save_preferences(user["id"], body.model_dump())
    return {"preferences": prefs}


@app.get("/api/search")
def search(q: str = Query("", min_length=1), limit: int = Query(15, ge=1, le=40)):
    return {"results": horse_svc.search_horses(q, limit=limit, profiles=profiles())}


@app.get("/api/stallions")
def stallions(
    q: str = "",
    sort: str = "rank",
    farm: str = "",
    min_fee: Optional[int] = None,
    max_fee: Optional[int] = None,
    stud_year_min: Optional[int] = None,
    stud_year_max: Optional[int] = None,
    crop: str = "",
):
    rows = horse_svc.list_stallions(
        profiles=profiles(),
        q=q,
        sort=sort,
        farm=farm,
        min_fee=min_fee,
        max_fee=max_fee,
        stud_year_min=stud_year_min,
        stud_year_max=stud_year_max,
        crop=crop,
    )
    return {"stallions": rows, "total": len(rows)}


@app.get("/api/stallions/farms")
def stallion_farms():
    return {"farms": horse_svc.list_farms(profiles())}


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
        min_fee=body.min_fee,
        max_fee=body.max_fee,
    )
    if result.get("error") == "not_found":
        raise HTTPException(
            status_code=404,
            detail="That broodmare is not in the Crossr pedigree database yet.",
        )
    brood = result.get("broodmare") or {}
    if brood.get("mare"):
        profile = horse_svc.get_horse_profile(brood["mare"], profiles=profiles())
        if profile:
            brood["pedigree"] = profile.get("pedigree")
            brood["race_record"] = profile.get("race_record")
            brood["race_totals"] = profile.get("race_totals")
            brood["inbreeding"] = profile.get("inbreeding")
    return result


@app.get("/api/hypomating/lineage/{stallion}")
def hypomating_lineage(stallion: str, max_fee: Optional[int] = None):
    return hypomating_engine.lineage_options_payload(stallion, profiles(), budget_filter=max_fee)


@app.get("/api/hypomating/crosses/{stallion}")
def hypomating_crosses(stallion: str, limit: int = Query(20, ge=1, le=40)):
    return hypomating_engine.top_crosses_payload(main.PEDIGREE_DATABASE, stallion, limit=limit)


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
    sort: str = "hip",
    sex: Optional[str] = None,
    limit: int = Query(80, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return sales_svc.catalog_lots(catalog_id, sort=sort, sex=sex, limit=limit, offset=offset)


@app.get("/api/sales/lots/{lot_id}")
def sales_lot_detail(lot_id: int):
    payload = sales_svc.get_lot(lot_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Lot not found")
    sire = (payload.get("lot") or {}).get("sire")
    if sire:
        payload["similar_crosses"] = hypomating_engine.top_crosses_payload(
            main.PEDIGREE_DATABASE, sire, limit=8
        ).get("crosses", [])
        dam = (payload.get("lot") or {}).get("dam")
        if dam:
            dam_profile = horse_svc.get_horse_profile(dam, profiles=profiles())
            payload["dam_family"] = dam_profile.get("pedigree") if dam_profile else None
    else:
        payload["similar_crosses"] = []
        payload["dam_family"] = None
    return payload


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

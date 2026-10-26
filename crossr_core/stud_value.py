"""
Colt breeding value from comparable stallions (fitted by scripts/train_stud_value.py).

A colt's breeding value is what his sire's colts are worth at stud on average:

    value per colt = Σ (initial stud fee of each son that went to stud × STUD_DEAL_MULTIPLIER)
                     / (sire's colts in crops old enough for sons to reach stud)

For a sire whose crops are too young for that to be measured, the value is
predicted from stallions that looked like him at the same point in their career:
a two-part model (chance any son reaches stud × size given some do) on initial
stud fee and how his fee has moved since, fitted per career stage. Once a sire has
enough mature crops his own record is blended in, weighted by how many colts it
rests on. The p25-p75 range is the spread of per-colt values among stallions like
him, so it includes the $0 most sires produce.

Pure Python at runtime; the artifact (stallion table + coefficients) lives in
Postgres crossr_models under MODEL_NAME.
"""

from __future__ import annotations

import math
import re
import threading
from collections import defaultdict
from typing import Any, Dict, List, Optional

MODEL_NAME = "stud_value"

# Lifetime stud value of a stallion ≈ initial stud fee × 400 (project notebook rule).
STUD_DEAL_MULTIPLIER = 400
# A crop counts toward a sire's own record once its colts could have retired to stud.
MATURE_CROP_AGE = 8
# Initial stud fee = fee in the first season, allowing a year either way for late listings.
ISF_WINDOW = (-1, 2)
MAX_STAGE = 12
# Years without mares bred that mark a different, same-named stallion.
NAMESAKE_GAP = 3
Z25 = -0.6744897501960817


def stallion_key(name: Any) -> str:
    """breeding_seasons disambiguates same-name stallions as 'Name (2)'; match on the name."""
    from crossr_core.sample_db import name_key

    return name_key(re.sub(r"\s*\(\d+\)\s*$", "", str(name or "")))


def _num(raw: Any) -> float:
    try:
        return float(str(raw).replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------- stallion table
def build_table(fees: Dict[str, Dict[int, int]], breeding_rows: List[dict], race_horse_rows: List[dict]) -> Dict[str, dict]:
    """name_key -> {first, foals{crop}, bred{year}, fees{year}, sire}. Every stallion that bred mares or has a fee."""
    from crossr_core.sample_db import name_key

    # breeding_seasons lists some stallions under numbered names ('Into Mischief (26)')
    # in some years; those are the same horse, so merge on the bare name.
    all_foals: Dict[str, Dict[int, float]] = defaultdict(dict)
    all_bred: Dict[str, Dict[int, float]] = defaultdict(dict)
    for row in breeding_rows:
        key = stallion_key(row.get("stallion"))
        try:
            year = int(str(row.get("breeding_year")).strip())
        except ValueError:
            continue
        if not key:
            continue
        all_foals[key][year + 1] = all_foals[key].get(year + 1, 0.0) + _num(row.get("live_foals"))
        all_bred[key][year] = all_bred[key].get(year, 0.0) + _num(row.get("mares_bred"))
    foals: Dict[str, Dict[int, float]] = {}
    bred: Dict[str, Dict[int, float]] = {}
    for key, years in all_bred.items():
        # A same-named older stallion shows up as seasons before a 3+ year gap
        # with no mares bred; keep only the latest unbroken run.
        seasons = sorted(y for y, n in years.items() if n > 0)
        start = seasons[0] if seasons else min(years)
        for prev, cur in zip(seasons, seasons[1:]):
            if cur - prev >= NAMESAKE_GAP:
                start = cur
        bred[key] = {y: n for y, n in years.items() if y >= start}
        foals[key] = {c: n for c, n in all_foals[key].items() if c >= start + 1}
    sire_of: Dict[str, str] = {}
    for row in race_horse_rows:
        key = name_key(row.get("name_key") or row.get("display_name") or "")
        if key and row.get("sire") and key not in sire_of:
            sire_of[key] = name_key(row["sire"])
    table: Dict[str, dict] = {}
    for key in set(bred) | set(fees):
        seasons = [y for y, n in bred.get(key, {}).items() if n > 0]
        fee_years = sorted(fees.get(key, {}))
        first = min(seasons) if seasons else (fee_years[0] if fee_years else None)
        if first is None:
            continue
        table[key] = {
            "first": first,
            "foals": dict(foals.get(key, {})),
            "bred": dict(bred.get(key, {})),
            "fees": dict(fees.get(key, {})),
            "sire": sire_of.get(key, ""),
        }
    return table


def initial_fee(entry: dict) -> Optional[float]:
    fees, first = entry.get("fees") or {}, entry["first"]
    years = [y for y in fees if first + ISF_WINDOW[0] <= y <= first + ISF_WINDOW[1]]
    return float(fees[min(years)]) if years else None


def fee_at(entry: dict, year: int) -> Optional[float]:
    fees = entry.get("fees") or {}
    years = [y for y in fees if y <= year]
    return float(fees[max(years)]) if years else None


class Imputer:
    """Initial fee for sons with none on file, from their first-season book (fit in training)."""

    def __init__(self, a: float, b: float, sd: float):
        self.a, self.b, self.sd = a, b, sd

    def __call__(self, entry: dict) -> Optional[float]:
        isf = initial_fee(entry)
        if isf:
            return isf
        book = (entry.get("bred") or {}).get(entry["first"], 0.0)
        if book <= 0:
            return None
        return math.exp(self.a + self.b * math.log(book) + self.sd * self.sd / 2.0)


def sons_index(table: Dict[str, dict]) -> Dict[str, List[str]]:
    sons: Dict[str, List[str]] = defaultdict(list)
    for key, entry in table.items():
        if entry.get("sire"):
            sons[entry["sire"]].append(key)
    return sons


def own_record(key: str, table: Dict[str, dict], sons: Dict[str, List[str]], impute: Imputer, through: int) -> Optional[dict]:
    """Per-colt stud value from the sire's mature crops as known in `through`."""
    entry = table.get(key)
    if not entry:
        return None
    crops = [c for c, n in entry["foals"].items() if c <= through - MATURE_CROP_AGE and n > 0]
    n_foals = sum(entry["foals"][c] for c in crops)
    if n_foals <= 0:
        return None
    total, n_sons = 0.0, 0
    for son in sons.get(key, []):
        se = table[son]
        # son foaled in a mature crop (first season ≈ foal year + 4) and already at stud
        if se["first"] > through or se["first"] - 4 > through - MATURE_CROP_AGE:
            continue
        isf = impute(se)
        if isf:
            total += isf * STUD_DEAL_MULTIPLIER
            n_sons += 1
    return {"value_per_colt": total / (n_foals / 2.0), "colts": n_foals / 2.0, "sons_at_stud": n_sons}


def features(entry: dict, stage: int) -> Optional[Dict[str, float]]:
    isf = initial_fee(entry)
    if not isf:
        return None
    fee_now = fee_at(entry, entry["first"] + stage) or isf
    return {
        "log_isf": math.log(isf),
        "fee_change": math.log(fee_now / isf),
        "cohort": (entry["first"] - 2005) / 10.0,
    }


# ---------------------------------------------------------------- prediction
def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z)) if z >= 0 else math.exp(z) / (1.0 + math.exp(z))


def _lin(coef: Dict[str, float], f: Dict[str, float]) -> float:
    return coef["intercept"] + sum(v * f[k] for k, v in coef.items() if k != "intercept")


def _mixture_quantile(p_any: float, mu: float, sigma: float, q: float) -> float:
    """Quantile of: 0 with prob 1 - p_any, else lognormal(mu, sigma)."""
    if q <= 1.0 - p_any:
        return 0.0
    from statistics import NormalDist

    z = NormalDist().inv_cdf((q - (1.0 - p_any)) / p_any)
    return math.exp(mu + sigma * z)


def predict_entry(entry: dict, model: Dict[str, Any], year: int) -> Optional[Dict[str, Any]]:
    stage = max(1, min(year - entry["first"], MAX_STAGE))
    block = model["stages"].get(str(stage))
    f = features(entry, stage)
    if not block or f is None:
        return None
    p_any = _sigmoid(_lin(block["any"], f))
    mu = _lin(block["size"], f)
    sigma = block["sigma"]
    return {
        "stage": stage,
        "p_any_son_at_stud": p_any,
        "mean": p_any * math.exp(mu + sigma * sigma / 2.0),
        "p25": _mixture_quantile(p_any, mu, sigma, 0.25),
        "p75": _mixture_quantile(p_any, mu, sigma, 0.75),
        "features": f,
    }


_LOCK = threading.Lock()
_MODEL: Optional[Dict[str, Any]] = None
_LOADED = False


def load(force: bool = False) -> Optional[Dict[str, Any]]:
    global _MODEL, _LOADED
    with _LOCK:
        if _LOADED and not force:
            return _MODEL
        _LOADED = True
        try:
            from crossr_core import railway_db

            _MODEL = railway_db.read_model(MODEL_NAME)
        except Exception:
            _MODEL = None
        return _MODEL


def colt_value(sire: str, year: int, model: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Expected breeding value of one colt by `sire`, as of `year`; None when the sire is unknown."""
    model = model or load()
    if not model:
        return None
    from crossr_core.sample_db import name_key

    key = name_key(sire)
    entry = model["stallions"].get(key)
    if not entry:
        return None
    entry = {**entry, "fees": {int(y): v for y, v in entry["fees"].items()}}
    pred = predict_entry(entry, model, year)
    own = entry.get("own")
    if pred is None and own is None:
        return None
    k = model["own_k"]
    if own is not None and pred is not None:
        w = own["colts"] / (own["colts"] + k)
        mean = w * own["value_per_colt"] + (1 - w) * pred["mean"]
        basis = f"own record ({own['sons_at_stud']} sons at stud from {own['colts']:,.0f} colts) blended {w:.0%} with comparable stallions"
    elif own is not None:
        w, mean = 1.0, own["value_per_colt"]
        basis = f"own record: {own['sons_at_stud']} sons at stud from {own['colts']:,.0f} colts"
    else:
        w, mean = 0.0, pred["mean"]
        basis = "comparable stallions at the same career stage (no mature crops yet)"
    low = pred["p25"] if pred else None
    high = pred["p75"] if pred else None
    if own is not None and pred is not None:
        # same quantity on both ends: shift the comparable-stallion spread to the blended centre
        scale = mean / pred["mean"] if pred["mean"] > 0 else 1.0
        low, high = low * scale, high * scale
    return {
        "point": mean,
        "low": low,
        "high": high,
        "own_weight": w,
        "own": own,
        "prediction": pred,
        "comparables": entry.get("comparables") or [],
        "basis": basis,
        "first_season": entry["first"],
        "initial_fee": initial_fee(entry),
        "fee_now": fee_at(entry, year),
    }

"""Wire PriceProjection + ValueProjector into sales Expected Market / Market Prediction."""

from __future__ import annotations

import math
import threading
from typing import Any, Dict, Optional

_LOCK = threading.Lock()
_PRICE_ROWS = None
_PRICE_MODEL = None
_PRICE_ERROR = None
_WARMED = False


def _money(amount: Optional[float]) -> str:
    if amount is None or (isinstance(amount, float) and (math.isnan(amount) or amount <= 0)):
        return ""
    return f"${int(round(amount)):,}"


def _fee_amount(raw: Any) -> int:
    if isinstance(raw, (int, float)) and raw > 0:
        return int(raw)
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    try:
        return int(digits) if digits else 0
    except ValueError:
        return 0


def _sold_as_kind(sold_as: str = "", catalog_title: str = "", sex: str = "") -> Optional[str]:
    """Return Yearling/Weanling for PriceProjection scope; else None.

    Prefer explicit sold_as. Catalog title is only a fallback when sold_as is blank
    or already yearling/weanling — never override broodmare / racing-age labels.
    """
    sold_u = (sold_as or "").strip().upper()
    if "WEANLING" in sold_u:
        return "Weanling"
    if "YEARLING" in sold_u:
        return "Yearling"
    if sold_u and any(
        tok in sold_u
        for tok in (
            "BROODMARE",
            "RACING AGE",
            "RACING PROSPECT",
            "TWO-YEAR",
            "2-YEAR",
            "2YO",
            "THREE-YEAR",
            "HORSE OF RACING",
        )
    ):
        return None
    blob = f"{catalog_title} {sex}".upper()
    if "WEANLING" in blob:
        return "Weanling"
    if "YEARLING" in blob:
        return "Yearling"
    return None


def warm_price_model(force: bool = False) -> Dict[str, Any]:
    """Build (once) the yearling/weanling price↔fee model. Safe to call at startup."""
    global _PRICE_ROWS, _PRICE_MODEL, _PRICE_ERROR, _WARMED
    with _LOCK:
        if _WARMED and not force:
            return {
                "ready": _PRICE_MODEL is not None,
                "n_matched": (_PRICE_MODEL or {}).get("n_matched", 0),
                "error": _PRICE_ERROR,
            }
        try:
            import PriceProjection as pp

            rows, _stats, model = pp.build_dataset(scrape_missing=False, max_scrapes=0)
            _PRICE_ROWS = rows
            _PRICE_MODEL = model
            _PRICE_ERROR = None
        except Exception as exc:  # pragma: no cover
            _PRICE_ROWS = None
            _PRICE_MODEL = None
            _PRICE_ERROR = str(exc)
        _WARMED = True
        return {
            "ready": _PRICE_MODEL is not None,
            "n_matched": (_PRICE_MODEL or {}).get("n_matched", 0),
            "error": _PRICE_ERROR,
        }


def _model() -> Optional[Dict[str, Any]]:
    if not _WARMED:
        warm_price_model()
    return _PRICE_MODEL


def _rows():
    if not _WARMED:
        warm_price_model()
    return _PRICE_ROWS or []


def resolve_stud_fee(sire_name: str, sire_profile: Optional[dict] = None) -> Optional[int]:
    fee = None
    try:
        import fee_and_standing_location as fee_db

        fee = fee_db.get_current_fee(sire_name or "")
    except Exception:
        fee = None
    if fee and fee > 0:
        return int(fee)
    profile_fee = _fee_amount((sire_profile or {}).get("Stud Fee"))
    return profile_fee or None


def _value_projector_payload(lot: dict) -> Dict[str, Any]:
    try:
        import ValueProjector as vp

        raw = vp.project_hip_value(
            sex=lot.get("sex_letter") or lot.get("sex") or "",
            sire=lot.get("sire") or "",
            dam=lot.get("dam") or "",
            horse_name=lot.get("name") or lot.get("raw_name") or "",
            sold_as=lot.get("sold_as") or "",
            covering_sire=lot.get("covering_sire") or "",
            sire_of_dam=lot.get("damsire") or lot.get("sire_of_dam") or "",
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc), "display": "", "point": None}

    point = raw.get("point")
    low = raw.get("low")
    high = raw.get("high")
    return {
        "ok": bool(point) or bool(raw.get("display")),
        "kind": raw.get("kind"),
        "role": raw.get("role"),
        "point": point,
        "low": low,
        "high": high,
        "display": raw.get("display") or raw.get("VALUE PROJECTOR") or "",
        "detail": raw.get("detail") or "",
        "projected_race_earnings": raw.get("PROJECTED RACE EARNINGS") or "",
        "race_detail": raw.get("race_detail") or "",
    }


def _price_projection_payload(
    *,
    sire: str,
    fee: Optional[int],
    sold_as: str,
) -> Dict[str, Any]:
    model = _model()
    if not model or not fee:
        return {
            "ok": False,
            "error": _PRICE_ERROR or ("no stud fee" if not fee else "model unavailable"),
            "sold_as": sold_as,
            "current_fee": fee,
        }
    try:
        import PriceProjection as pp

        proj = pp.project_price(float(fee), model, sold_as=sold_as)
        hist = pp.summarize_sire_history(_rows(), sire) if sire else {"n": 0}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "sold_as": sold_as, "current_fee": fee}

    if proj.get("error"):
        return {"ok": False, "error": proj["error"], "sold_as": sold_as, "current_fee": fee}

    low = proj.get("proj_median_multiple")
    high = proj.get("proj_mean_multiple") or proj.get("proj_loglog")
    point = proj.get("proj_loglog") or proj.get("proj_median_multiple")
    if low and high and high < low:
        low, high = high, low
    if low and high:
        label = f"{_money(low)} – {_money(high)}"
    elif point:
        label = _money(point)
        low = high = point
    else:
        label = ""

    market_block = (model.get("by_kind") or {}).get(sold_as) or (model.get("by_kind") or {}).get("All") or {}
    return {
        "ok": bool(label),
        "sold_as": sold_as,
        "current_fee": fee,
        "n": proj.get("n"),
        "n_matched": model.get("n_matched"),
        "median_multiple": proj.get("median_multiple"),
        "mean_multiple": proj.get("mean_multiple"),
        "proj_median_multiple": proj.get("proj_median_multiple"),
        "proj_mean_multiple": proj.get("proj_mean_multiple"),
        "proj_loglog": proj.get("proj_loglog"),
        "low": low,
        "high": high,
        "mid": ((low or 0) + (high or 0)) / 2.0 if low and high else point,
        "point": point,
        "label": label,
        "market_median_multiple": market_block.get("median_multiple"),
        "market_mean_multiple": market_block.get("mean_multiple"),
        "sire_history": {
            "n": hist.get("n") or 0,
            "median_price": hist.get("median_price"),
            "median_multiple": hist.get("median_multiple"),
            "mean_multiple": hist.get("mean_multiple"),
            "years": hist.get("years") or [],
        },
    }


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _market_prediction(price: Dict[str, Any], value: Dict[str, Any], fee: Optional[int]) -> Dict[str, Any]:
    """
    Boom/bust signal for the Market Prediction panel.

    Prefer sire historical multiples vs market; else breeding-value vs auction projection.
    """
    score = 0.0
    basis = "market baseline"
    market_med = price.get("market_median_multiple")
    hist = price.get("sire_history") or {}
    hist_n = int(hist.get("n") or 0)
    hist_med = hist.get("median_multiple")

    if hist_n >= 5 and market_med and hist_med:
        # Sires that historically clear above market multiples → boom sale signal
        ratio = float(hist_med) / float(market_med)
        score = _clamp((ratio - 1.0) / 0.5)  # ±50% multiple → ±1
        basis = f"sire progeny {hist_med:.2f}× vs market {market_med:.2f}× (n={hist_n})"
    elif value.get("ok") and price.get("mid") and value.get("point"):
        # Rich auction vs breeding value → boom (hot sale); cheap auction → soft/bust
        ratio = float(price["mid"]) / max(float(value["point"]), 1.0)
        score = _clamp((ratio - 1.0) / 0.75)
        basis = f"auction mid {_money(price['mid'])} vs breeding value {_money(value['point'])}"
    elif price.get("ok") and fee and market_med:
        # Fee-tier model multiple vs market median multiple
        proj_mult = (price.get("point") or price.get("mid") or 0) / float(fee)
        ratio = proj_mult / float(market_med) if market_med else 1.0
        score = _clamp((ratio - 1.0) / 0.35)
        basis = f"model multiple {proj_mult:.2f}× vs market {market_med:.2f}×"

    if score >= 0.55:
        signal, label = "boom", "Boom"
    elif score >= 0.2:
        signal, label = "firm", "Firm"
    elif score <= -0.55:
        signal, label = "bust", "Bust"
    elif score <= -0.2:
        signal, label = "soft", "Soft"
    else:
        signal, label = "fair", "Fair"

    # Marker along the boom→bust curve (0 left boom, 0.5 peak, 1 right)
    marker = 0.5 - (score * 0.42)
    marker = max(0.08, min(0.92, marker))

    note_bits = [f"{label} — {basis}."]
    if price.get("ok") and price.get("label"):
        note_bits.append(
            f"Projected {price.get('sold_as', 'sale').lower()} "
            f"{price['label']} on {_money(fee)} stud fee "
            f"({price.get('median_multiple') or 0:.2f}× median / "
            f"{price.get('mean_multiple') or 0:.2f}× mean)."
        )
    if value.get("ok") and value.get("display"):
        race = value.get("projected_race_earnings") or ""
        extra = f" Value projector {value['display']}"
        if race:
            extra += f"; race earnings {race}"
        note_bits.append(extra + ".")

    return {
        "signal": signal,
        "label": label,
        "score": round(score, 3),
        "marker": round(marker, 3),
        "basis": basis,
        "note": " ".join(note_bits),
        "ready": bool(price.get("ok") or value.get("ok")),
    }


def project_lot_market(
    lot: Optional[dict] = None,
    *,
    sire: str = "",
    sex: str = "",
    sold_as: str = "",
    catalog_title: str = "",
    sire_profile: Optional[dict] = None,
    dam: str = "",
    name: str = "",
    damsire: str = "",
    covering_sire: str = "",
) -> Dict[str, Any]:
    """Combined Expected Market Value + Market Prediction for one hip."""
    lot = dict(lot or {})
    if sire:
        lot.setdefault("sire", sire)
    if sex:
        lot.setdefault("sex_letter", sex)
        lot.setdefault("sex", sex)
    if sold_as:
        lot.setdefault("sold_as", sold_as)
    if dam:
        lot.setdefault("dam", dam)
    if name:
        lot.setdefault("name", name)
    if damsire:
        lot.setdefault("damsire", damsire)
    if covering_sire:
        lot.setdefault("covering_sire", covering_sire)

    kind = _sold_as_kind(
        lot.get("sold_as") or "",
        catalog_title,
        lot.get("sex_letter") or lot.get("sex") or "",
    )
    # ValueProjector sale-type gates on sold_as; fill from catalog when missing.
    if kind and "YEARLING" not in (lot.get("sold_as") or "").upper() and "WEANLING" not in (
        lot.get("sold_as") or ""
    ).upper():
        lot["sold_as"] = kind
    fee = resolve_stud_fee(lot.get("sire") or "", sire_profile)
    value = _value_projector_payload(lot)
    price = (
        _price_projection_payload(sire=lot.get("sire") or "", fee=fee, sold_as=kind)
        if kind
        else {"ok": False, "error": "not yearling/weanling", "sold_as": sold_as or None}
    )

    # Expected Market Value: auction projection for Y/W; else Value Projector band.
    if price.get("ok"):
        expected = {
            "sire_stud_fee": fee,
            "low": price.get("low"),
            "high": price.get("high"),
            "mid": price.get("mid"),
            "label": price.get("label"),
            "rule": f"PriceProjection {kind} median–mean stud-fee multiple",
            "source": "price_projection",
            "sold_as": kind,
            "median_multiple": price.get("median_multiple"),
            "mean_multiple": price.get("mean_multiple"),
            "proj_loglog": price.get("proj_loglog"),
            "n": price.get("n"),
        }
    elif value.get("ok") and (value.get("low") or value.get("point")):
        low = value.get("low") if value.get("low") is not None else value.get("point")
        high = value.get("high") if value.get("high") is not None else value.get("point")
        expected = {
            "sire_stud_fee": fee,
            "low": low,
            "high": high,
            "mid": ((low or 0) + (high or 0)) / 2.0 if low and high else value.get("point"),
            "label": value.get("display") or (_money(low) if low == high else f"{_money(low)} – {_money(high)}"),
            "rule": f"ValueProjector {value.get('kind') or 'breeding value'}",
            "source": "value_projector",
            "sold_as": kind,
        }
    elif fee:
        low, high = fee * 2, fee * 6
        expected = {
            "sire_stud_fee": fee,
            "low": low,
            "high": high,
            "mid": (low + high) / 2.0,
            "label": f"{_money(low)} – {_money(high)}",
            "rule": "fallback 2×–6× sire stud fee",
            "source": "fee_fallback",
            "sold_as": kind,
        }
    else:
        expected = {
            "sire_stud_fee": None,
            "low": None,
            "high": None,
            "mid": None,
            "label": "Projection unavailable (stud fee unknown)",
            "rule": "unavailable",
            "source": "unavailable",
            "sold_as": kind,
        }

    expected["value_projector"] = value
    expected["price_projection"] = {
        k: price.get(k)
        for k in (
            "ok",
            "error",
            "sold_as",
            "current_fee",
            "n",
            "n_matched",
            "median_multiple",
            "mean_multiple",
            "proj_median_multiple",
            "proj_mean_multiple",
            "proj_loglog",
            "market_median_multiple",
            "sire_history",
        )
        if k in price
    }

    prediction = _market_prediction(price if price.get("ok") else {}, value, fee)
    return {
        "expected_market": expected,
        "market_prediction": prediction,
    }


def expected_market_mid_for_filter(
    sire_name: str,
    *,
    sold_as: str = "",
    catalog_title: str = "",
    sex: str = "",
    sire_profile: Optional[dict] = None,
) -> Dict[str, Any]:
    """Cheap band for catalog price filters (PriceProjection mid when possible)."""
    kind = _sold_as_kind(sold_as, catalog_title, sex) or "Yearling"
    fee = resolve_stud_fee(sire_name, sire_profile)
    price = _price_projection_payload(sire=sire_name or "", fee=fee, sold_as=kind)
    if price.get("ok") and price.get("mid"):
        return {
            "low": price.get("low"),
            "high": price.get("high"),
            "mid": price.get("mid"),
            "source": "price_projection",
            "label": price.get("label"),
            "sire_stud_fee": fee,
        }
    if fee:
        low, high = fee * 2, fee * 6
        return {
            "low": low,
            "high": high,
            "mid": (low + high) / 2.0,
            "source": "fee_fallback",
            "label": f"{_money(low)} – {_money(high)}",
            "sire_stud_fee": fee,
        }
    return {
        "low": None,
        "high": None,
        "mid": None,
        "source": "unavailable",
        "label": "",
        "sire_stud_fee": None,
    }

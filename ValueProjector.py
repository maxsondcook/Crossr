"""
ValueProjector — expected breeding-value (E[BV]) projections for colts and fillies/mares.

Formulas from project notes:

  COLT
    E[BV] = Σ_i (ISF_i · 400) / (F_SS_i / 2)
    where similar stallions S_i are sons/grandsons of the sire (or of the
    sire's sire when the direct sire has no sons at stud yet).
    Horses that never stand at stud contribute 0. Mode of the distribution
    is 0; this module estimates the mean (expected value).
    Industry stud-deal heuristic: lifetime stud value ≈ ISF × 400.

  FILLY / MARE
    E[BV] ≈ Σ progeny auction prices (empirical), isolating the mare's
    added value as sale_price / covering_sire_stud_fee (e.g. 2×, 6×).
    Career scale: ~6–10 foals/broodmare × ≈75% live-foal rate.
    When grandchildren / progeny sales are missing, fall back to familial
    bonds and stallions with similar race records / similar ISF.

  RACE EARNINGS (stallion projection)
    (Earnings / runner) · (runners / # foals with age ≥ 3)
    If the horse has no runners yet, predict via similar-ISF peers.
"""

from __future__ import annotations

import csv
import math
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pedigrees_database
import stallion_profiles as sp_mod

# ---------------------------------------------------------------------------
# Constants (from notebook)
# ---------------------------------------------------------------------------
STUD_DEAL_MULTIPLIER = 400
LIVE_FOAL_RATE = 0.75
FOALS_PER_BROODMARE_LOW = 6
FOALS_PER_BROODMARE_HIGH = 10
FOALS_PER_BROODMARE_MEAN = 8
EXPECTED_LIVE_FOALS = FOALS_PER_BROODMARE_MEAN * LIVE_FOAL_RATE  # 6.0

# Opening / initial stud fees when known (current profile fee is used otherwise).
# Notebook example: Flightline ISF = $200,000.
INITIAL_STUD_FEE_OVERRIDES: Dict[str, int] = {
    "FLIGHTLINE": 200_000,
}

SALES_DIRS = [Path("sales_data"), Path(".")]

# Broodmare-sire development timeline (informational)
BM_SIRE_TIMELINE = [
    ("Horse retires", "Age 3–5"),
    ("First season at stud", "Age 4–6"),
    ("First foals", "Age 5–7"),
    ("First runners", "Age 7–9"),
    ("First horses retire", "Age 8–10"),
    ("First grandchildren", "Age 10–12"),
    ("First grandchildren at sales", "Age 11–13"),
]

# Lazy sales index: dam_sire_key -> list of sale dicts
_SALES_BY_DAM_SIRE: Optional[Dict[str, List[dict]]] = None
_SALES_BY_DAM: Optional[Dict[str, List[dict]]] = None


# ---------------------------------------------------------------------------
# Name / money helpers
# ---------------------------------------------------------------------------
def clean_horse_name(name: str) -> str:
    if not name or not isinstance(name, str):
        return ""
    cleaned = re.sub(r"\(.*?\)", "", name)
    cleaned = cleaned.replace(".", "").replace("'", "").replace(",", "")
    return " ".join(cleaned.split()).strip().upper()


def parse_money(val: Any) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().upper().replace(",", "").replace("$", "")
    if not s or any(tok in s for tok in ("OUT", "NOT SOLD", "RNA", "N/A", "-2.00")):
        return 0.0
    cleaned = "".join(c for c in s if c.isdigit() or c == ".")
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def fmt_money(amount: float) -> str:
    if amount is None or (isinstance(amount, float) and math.isnan(amount)):
        return "n/a"
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.0f}"


def _profile_lookup(name: str) -> Tuple[Optional[str], Optional[dict]]:
    """Return (canonical profile key, profile dict) or (None, None)."""
    profiles = sp_mod.stallion_profiles
    target = clean_horse_name(name)
    for key, data in profiles.items():
        if clean_horse_name(key) == target:
            return key, data
    # Soft contains match
    hits = [k for k in profiles if target and target in clean_horse_name(k)]
    if len(hits) == 1:
        return hits[0], profiles[hits[0]]
    return None, None


def _pedigree_for(name: str) -> Optional[dict]:
    key = clean_horse_name(name)
    ped = pedigrees_database.pedigree_map.get(key)
    if ped:
        return ped
    # Soft match
    for k, v in pedigrees_database.pedigree_map.items():
        if clean_horse_name(k) == key:
            return v
    return None


def _node_horse(node: Any) -> str:
    if isinstance(node, dict):
        return clean_horse_name(node.get("Horse", ""))
    return clean_horse_name(str(node) if node else "")


def get_sire_name(name: str) -> Optional[str]:
    ped = _pedigree_for(name)
    if not ped:
        return None
    s = _node_horse(ped.get("Sire"))
    return s or None


def get_grandsire_name(name: str) -> Optional[str]:
    ped = _pedigree_for(name)
    if not ped:
        return None
    sire = ped.get("Sire")
    if isinstance(sire, dict):
        return _node_horse(sire.get("Sire")) or None
    return None


def get_dam_sire_name(name: str) -> Optional[str]:
    ped = _pedigree_for(name)
    if not ped:
        return None
    dam = ped.get("Dam")
    if isinstance(dam, dict):
        return _node_horse(dam.get("Sire")) or None
    return None


def career_race_earnings(profile: dict) -> float:
    total = 0.0
    for season in (profile.get("Race Record") or {}).values():
        if isinstance(season, dict):
            total += parse_money(season.get("Earnings", 0))
    return total


def initial_stud_fee(name: str, profile: Optional[dict] = None) -> float:
    """ISF: override table first, else current Stud Fee from the profile."""
    key = clean_horse_name(name)
    if key in INITIAL_STUD_FEE_OVERRIDES:
        return float(INITIAL_STUD_FEE_OVERRIDES[key])
    if profile is None:
        _, profile = _profile_lookup(name)
    if not profile:
        return 0.0
    return parse_money(profile.get("Stud Fee", 0))


def foals_of_racing_age(name: str, profile: Optional[dict] = None) -> int:
    if profile is None:
        _, profile = _profile_lookup(name)
    if profile:
        prog = profile.get("Progeny Racing Statistics") or {}
        for field in ("Foals of Racing Age", "Foals"):
            raw = prog.get(field)
            if raw is not None:
                try:
                    n = int(raw)
                    if n > 0:
                        return n
                except (TypeError, ValueError):
                    pass
    # Broodmare-sire cum_foals as last resort for prolific older sires
    try:
        from broodmare_sire_data import broodmare_sire_raw, clean_horse_name as bms_clean

        target = bms_clean(name)
        for entry in broodmare_sire_raw:
            if bms_clean(entry["stallion"]) == target:
                n = int(entry.get("cum_foals") or 0)
                if n > 0:
                    return n
    except Exception:
        pass
    return 0


def stands_at_stud(profile: dict) -> bool:
    fee = parse_money(profile.get("Stud Fee", 0))
    status = str(profile.get("Status", "")).lower()
    if fee <= 0:
        return False
    if any(tok in status for tok in ("pension", "dead", "deceased", "retired from stud")):
        return False
    return True


# ---------------------------------------------------------------------------
# Similar stallions (sons / grandsons)
# ---------------------------------------------------------------------------
def find_similar_stallions(
    anchor_sire: str,
    include_grandsons: bool = True,
    exclude_names: Optional[set] = None,
) -> List[Tuple[str, dict]]:
    """
    Stallions in the roster whose sire (or grandsire) is anchor_sire.
    Only horses that currently stand at stud (fee > 0) are returned;
    non-stud horses contribute BV = 0 by omission from the sum.
    """
    exclude = {clean_horse_name(n) for n in (exclude_names or set())}
    anchor = clean_horse_name(anchor_sire)
    results: List[Tuple[str, dict]] = []

    for name, profile in sp_mod.stallion_profiles.items():
        if clean_horse_name(name) in exclude:
            continue
        if not stands_at_stud(profile):
            continue
        sire = get_sire_name(name)
        gs = get_grandsire_name(name) if include_grandsons else None
        if sire == anchor or (include_grandsons and gs == anchor):
            results.append((name, profile))

    results.sort(key=lambda x: initial_stud_fee(x[0], x[1]), reverse=True)
    return results


def resolve_sire_of_stallions(colt_sire: str) -> Tuple[str, str]:
    """
    Choose the Sire-of-Stallions (SS) used for F_SS and the similar set.

    Prefer the colt's own sire when he already has sons/grandsons at stud.
    Otherwise walk up one generation (notebook: Flightline → Tapit side).
    """
    direct = clean_horse_name(colt_sire)
    similars = find_similar_stallions(direct)
    if similars:
        return direct, "direct"

    parent = get_sire_name(colt_sire)
    if parent:
        return parent, "sire_side_fallback"

    return direct, "direct_empty"


# ---------------------------------------------------------------------------
# Colt E[BV]
# ---------------------------------------------------------------------------
def colt_contribution(isf: float, foals_racing_age_ss: int) -> float:
    """Single similar-stallion term: (ISF · 400) / (F_SS / 2)."""
    male_foals = foals_racing_age_ss / 2.0
    if male_foals <= 0 or isf <= 0:
        return 0.0
    return (isf * STUD_DEAL_MULTIPLIER) / male_foals


def project_colt_bv(colt_sire: str, verbose: bool = True) -> dict:
    """
    Expected breeding value of a yearling/colt by `colt_sire`.

    E[BV] = Σ (ISF_i · 400) / (F_SS / 2) over similar stallions of SS.
    """
    canon_sire, sire_profile = _profile_lookup(colt_sire)
    display_sire = canon_sire or colt_sire.strip()

    ss_name, resolution = resolve_sire_of_stallions(display_sire)
    ss_canon, ss_profile = _profile_lookup(ss_name)
    ss_display = ss_canon or ss_name

    f_ss = foals_of_racing_age(ss_display, ss_profile)
    # Notebook ballpark for Tapit was ~3000; if profile is thin, allow BMS cum_foals
    if f_ss <= 0:
        try:
            from broodmare_sire_data import broodmare_sire_raw, clean_horse_name as bms_clean

            for entry in broodmare_sire_raw:
                if bms_clean(entry["stallion"]) == bms_clean(ss_display):
                    f_ss = int(entry.get("cum_foals") or 0)
                    break
        except Exception:
            pass

    similar = find_similar_stallions(ss_display)
    contributions = []
    total = 0.0

    for name, profile in similar:
        isf = initial_stud_fee(name, profile)
        if isf <= 0:
            continue  # BV = 0 if they don't stand
        term = colt_contribution(isf, f_ss)
        stud_deal = isf * STUD_DEAL_MULTIPLIER
        contributions.append(
            {
                "stallion": name,
                "isf": isf,
                "stud_deal": stud_deal,
                "contribution": term,
                "relation": (
                    "son"
                    if get_sire_name(name) == clean_horse_name(ss_display)
                    else "grandson"
                ),
            }
        )
        total += term

    result = {
        "kind": "colt",
        "colt_sire": display_sire,
        "sire_of_stallions": ss_display,
        "resolution": resolution,
        "foals_of_racing_age_ss": f_ss,
        "male_foals_est": f_ss / 2.0 if f_ss else 0.0,
        "n_similar": len(contributions),
        "contributions": contributions,
        "expected_bv": total,
        "note": (
            "Mode of realized BV is 0 (most colts never stand). "
            "This figure is the mean / expected value across similar stallions."
        ),
    }

    if verbose:
        _print_colt_report(result)
    return result


def _print_colt_report(r: dict) -> None:
    print("\n" + "=" * 72)
    print("  VALUE PROJECTOR — COLT BREEDING VALUE")
    print("=" * 72)
    print(f"  Colt sire              : {r['colt_sire']}")
    print(f"  Sire of stallions (SS) : {r['sire_of_stallions']}  [{r['resolution']}]")
    print(f"  F_SS (foals racing age): {r['foals_of_racing_age_ss']:,}")
    print(f"  Colts of racing age    : {r['male_foals_est']:,.0f}   (F_SS / 2)")
    print(f"  Similar stallions (n)  : {r['n_similar']}")
    print("-" * 72)
    print(f"  {'Stallion':<22} {'Rel':<9} {'ISF':>12} {'Stud deal':>14} {'Contrib':>12}")
    print("-" * 72)
    for c in r["contributions"]:
        print(
            f"  {c['stallion']:<22} {c['relation']:<9} "
            f"{fmt_money(c['isf']):>12} {fmt_money(c['stud_deal']):>14} "
            f"{fmt_money(c['contribution']):>12}"
        )
    print("-" * 72)
    print(f"  E[BV]  =  Σ (ISF·{STUD_DEAL_MULTIPLIER}) / (F_SS/2)")
    print(f"  Expected breeding value: {fmt_money(r['expected_bv'])}")
    print(f"  ({r['note']})")
    print("=" * 72 + "\n")


# ---------------------------------------------------------------------------
# Sales index (for filly / mare projections)
# ---------------------------------------------------------------------------
def _header_map(fieldnames: Optional[List[str]]) -> Dict[str, str]:
    if not fieldnames:
        return {}
    return {(h or "").lower().strip(): h for h in fieldnames if h}


def _dam_to_sire_cache() -> Dict[str, str]:
    """Map dam name → her sire (catalog 'sire of dam') from the pedigree DB."""
    cache: Dict[str, str] = {}
    for key, ped in pedigrees_database.pedigree_map.items():
        if not isinstance(ped, dict):
            continue
        dam_key = clean_horse_name(key)
        sire = _node_horse(ped.get("Sire"))
        if dam_key and sire:
            cache[dam_key] = sire
    return cache


def _build_sales_indexes() -> None:
    global _SALES_BY_DAM_SIRE, _SALES_BY_DAM
    by_ds: Dict[str, List[dict]] = defaultdict(list)
    by_dam: Dict[str, List[dict]] = defaultdict(list)
    dam_sire_of = _dam_to_sire_cache()

    for base in SALES_DIRS:
        if not base.exists():
            continue
        for fp in base.glob("*.csv"):
            try:
                with open(fp, mode="r", encoding="utf-8-sig", errors="ignore") as f:
                    reader = csv.DictReader(f)
                    hm = _header_map(reader.fieldnames)
                    sod_h = hm.get("sire of dam") or hm.get("bms") or hm.get("damsire")
                    sire_h = hm.get("sire")
                    dam_h = hm.get("dam")
                    price_h = hm.get("price")
                    sex_h = hm.get("sex")
                    name_h = hm.get("name") or hm.get("horse name") or hm.get("horse")
                    if not price_h:
                        continue
                    for row in reader:
                        price = parse_money(row.get(price_h))
                        if price <= 0:
                            continue
                        sire = clean_horse_name(row.get(sire_h, "")) if sire_h else ""
                        dam = clean_horse_name(row.get(dam_h, "")) if dam_h else ""
                        sod = clean_horse_name(row.get(sod_h, "")) if sod_h else ""

                        # Infer broodmare sire = the dam's own sire when SOD is absent
                        if not sod and dam:
                            sod = dam_sire_of.get(dam, "")

                        rec = {
                            "price": price,
                            "sire": sire,
                            "dam": dam,
                            "dam_sire": sod,
                            "sex": (row.get(sex_h, "") if sex_h else ""),
                            "horse": clean_horse_name(row.get(name_h, "")) if name_h else "",
                            "file": fp.name,
                        }
                        if sod:
                            by_ds[sod].append(rec)
                        if dam:
                            by_dam[dam].append(rec)
            except Exception:
                continue

    _SALES_BY_DAM_SIRE = dict(by_ds)
    _SALES_BY_DAM = dict(by_dam)


def sales_by_dam_sire(dam_sire: str) -> List[dict]:
    global _SALES_BY_DAM_SIRE
    if _SALES_BY_DAM_SIRE is None:
        _build_sales_indexes()
    assert _SALES_BY_DAM_SIRE is not None
    return list(_SALES_BY_DAM_SIRE.get(clean_horse_name(dam_sire), []))


def sales_by_dam(dam: str) -> List[dict]:
    global _SALES_BY_DAM
    if _SALES_BY_DAM is None:
        _build_sales_indexes()
    assert _SALES_BY_DAM is not None
    return list(_SALES_BY_DAM.get(clean_horse_name(dam), []))


def covering_sire_fee(sire_name: str) -> float:
    _, profile = _profile_lookup(sire_name)
    if profile:
        return initial_stud_fee(sire_name, profile)
    return 0.0


def added_value_multiplier(sale_price: float, stud_fee: float) -> Optional[float]:
    if stud_fee <= 0 or sale_price <= 0:
        return None
    return sale_price / stud_fee


# ---------------------------------------------------------------------------
# Similar ISF / race-record peers (fallback when data is thin)
# ---------------------------------------------------------------------------
def similar_isf_peers(
    reference_name: str,
    top_n: int = 5,
    exclude_self: bool = True,
) -> List[Tuple[str, dict, float]]:
    """
    Stallions with similar initial stud fee and race earnings.
    Distance = normalized |ΔISF| + normalized |Δcareer earnings|.
    """
    ref_key, ref_profile = _profile_lookup(reference_name)
    if not ref_profile:
        # Synthesize from name only — use broodmare / fee-less peers by earnings≈0
        ref_isf = INITIAL_STUD_FEE_OVERRIDES.get(clean_horse_name(reference_name), 0.0)
        ref_earn = 0.0
    else:
        ref_isf = initial_stud_fee(ref_key or reference_name, ref_profile)
        ref_earn = career_race_earnings(ref_profile)

    scored: List[Tuple[str, dict, float]] = []
    for name, profile in sp_mod.stallion_profiles.items():
        if exclude_self and clean_horse_name(name) == clean_horse_name(reference_name):
            continue
        if not stands_at_stud(profile):
            continue
        isf = initial_stud_fee(name, profile)
        earn = career_race_earnings(profile)
        # Relative distances; guard zeros
        isf_den = max(ref_isf, isf, 1.0)
        earn_den = max(ref_earn, earn, 1.0)
        dist = abs(isf - ref_isf) / isf_den + abs(earn - ref_earn) / earn_den
        scored.append((name, profile, dist))

    scored.sort(key=lambda x: x[2])
    return scored[:top_n]


# ---------------------------------------------------------------------------
# Filly / mare E[BV]
# ---------------------------------------------------------------------------
def project_filly_bv(
    name: str,
    mode: str = "auto",
    verbose: bool = True,
) -> dict:
    """
    Project breeding value for a filly / female / mare.

    mode:
      - "mare"  : treat `name` as a specific dam; sum her progeny auction prices
      - "bms"   : treat `name` as a broodmare sire (e.g. Tapit); use daughters'
                  progeny sales and added-value multipliers
      - "auto"  : if `name` is a known stallion profile → bms, else mare
    """
    canon, profile = _profile_lookup(name)
    if mode == "auto":
        mode = "bms" if profile else "mare"

    if mode == "mare":
        return _project_specific_mare(name, verbose=verbose)
    return _project_broodmare_sire_filly(canon or name, verbose=verbose)


def _project_specific_mare(dam_name: str, verbose: bool = True) -> dict:
    sales = sales_by_dam(dam_name)
    multipliers = []
    by_sire: Dict[str, List[float]] = defaultdict(list)

    for rec in sales:
        fee = covering_sire_fee(rec["sire"])
        mult = added_value_multiplier(rec["price"], fee)
        by_sire[rec["sire"] or "?"].append(rec["price"])
        if mult is not None:
            multipliers.append(
                {
                    "sire": rec["sire"],
                    "price": rec["price"],
                    "stud_fee": fee,
                    "multiplier": mult,
                }
            )

    total_auction = sum(r["price"] for r in sales)
    mean_mult = statistics.mean(m["multiplier"] for m in multipliers) if multipliers else None
    median_price = statistics.median(r["price"] for r in sales) if sales else None

    # Career projection if we only have a few foals so far
    projected_career = None
    if median_price is not None:
        projected_career = EXPECTED_LIVE_FOALS * median_price
    elif not sales:
        # Fall back via dam sire / similar ISF
        ds = get_sire_name(dam_name)  # mare's sire = broodmare sire of her foals' dams... wait
        # For a mare, her sire is the broodmare sire of her progeny.
        mare_sire = get_sire_name(dam_name)
        if mare_sire:
            proxy = _project_broodmare_sire_filly(mare_sire, verbose=False)
            projected_career = proxy.get("projected_career_bv")
            mean_mult = proxy.get("mean_added_value_multiplier")
        else:
            peers = similar_isf_peers(dam_name)
            # Use first peer that is a known BM sire in sales
            for peer_name, _, _ in peers:
                proxy_sales = sales_by_dam_sire(peer_name)
                if proxy_sales:
                    median_price = statistics.median(r["price"] for r in proxy_sales)
                    projected_career = EXPECTED_LIVE_FOALS * median_price
                    break

    result = {
        "kind": "mare",
        "name": dam_name.strip(),
        "progeny_sales_count": len(sales),
        "sum_progeny_auction": total_auction,
        "mean_added_value_multiplier": mean_mult,
        "multiplier_examples": multipliers[:10],
        "median_progeny_price": median_price,
        "expected_live_foals": EXPECTED_LIVE_FOALS,
        "projected_career_bv": projected_career if projected_career is not None else total_auction,
        "empirical_bv": total_auction,
        "by_covering_sire": {k: {"n": len(v), "mean": statistics.mean(v)} for k, v in by_sire.items()},
    }
    if verbose:
        _print_filly_report(result)
    return result


def _project_broodmare_sire_filly(bms_name: str, verbose: bool = True) -> dict:
    """
    Expected breeding value of a filly whose sire is `bms_name` (she will
    become a broodmare by that sire), using auction results of foals out of
    mares by that sire — isolating added value vs covering-sire stud fees.
    """
    display = bms_name.strip()
    sales = sales_by_dam_sire(display)
    used_fallback = False
    fallback_from = None

    if len(sales) < 5:
        # Familial bonds / similar ISF peers
        used_fallback = True
        peers = similar_isf_peers(display, top_n=8)
        for peer_name, _, dist in peers:
            peer_sales = sales_by_dam_sire(peer_name)
            if len(peer_sales) >= 5:
                sales = peer_sales
                fallback_from = peer_name
                break

    multipliers = []
    prices = []
    for rec in sales:
        prices.append(rec["price"])
        fee = covering_sire_fee(rec["sire"])
        mult = added_value_multiplier(rec["price"], fee)
        if mult is not None:
            multipliers.append(
                {
                    "sire": rec["sire"],
                    "price": rec["price"],
                    "stud_fee": fee,
                    "multiplier": mult,
                }
            )

    mean_price = statistics.mean(prices) if prices else None
    median_price = statistics.median(prices) if prices else None
    mean_mult = statistics.mean(m["multiplier"] for m in multipliers) if multipliers else None
    median_mult = (
        statistics.median(m["multiplier"] for m in multipliers) if multipliers else None
    )

    # Per-dam aggregation: average total progeny auction value among dams
    by_dam: Dict[str, float] = defaultdict(float)
    for rec in sales:
        if rec["dam"]:
            by_dam[rec["dam"]] += rec["price"]
    mean_per_dam = statistics.mean(by_dam.values()) if by_dam else None

    projected = None
    if median_price is not None:
        projected = EXPECTED_LIVE_FOALS * median_price
    elif mean_per_dam is not None:
        projected = mean_per_dam

    # Highlight notebook-style examples (highest / notable multipliers)
    examples = sorted(multipliers, key=lambda m: m["multiplier"], reverse=True)[:8]

    result = {
        "kind": "filly_bms",
        "name": display,
        "broodmare_sire": display,
        "progeny_sales_count": len(sales),
        "unique_dams": len(by_dam),
        "mean_progeny_price": mean_price,
        "median_progeny_price": median_price,
        "mean_added_value_multiplier": mean_mult,
        "median_added_value_multiplier": median_mult,
        "mean_total_per_dam": mean_per_dam,
        "expected_live_foals": EXPECTED_LIVE_FOALS,
        "foals_per_broodmare_range": (FOALS_PER_BROODMARE_LOW, FOALS_PER_BROODMARE_HIGH),
        "live_foal_rate": LIVE_FOAL_RATE,
        "projected_career_bv": projected,
        "empirical_bv": mean_per_dam,
        "multiplier_examples": examples,
        "used_similar_isf_fallback": used_fallback and fallback_from is not None,
        "fallback_peer": fallback_from,
    }
    if verbose:
        _print_filly_report(result)
    return result


def _print_filly_report(r: dict) -> None:
    print("\n" + "=" * 72)
    if r["kind"] == "mare":
        print("  VALUE PROJECTOR — MARE BREEDING VALUE (progeny at auction)")
    else:
        print("  VALUE PROJECTOR — FILLY / BMS BREEDING VALUE")
    print("=" * 72)
    print(f"  Subject                : {r['name']}")
    if r["kind"] == "filly_bms":
        print(f"  Broodmare sire lens    : {r['broodmare_sire']}")
        if r.get("used_similar_isf_fallback"):
            print(f"  Similar-ISF fallback   : using sales of {r['fallback_peer']}")
    print(f"  Progeny sales used     : {r.get('progeny_sales_count', 0):,}")
    if r.get("unique_dams") is not None:
        print(f"  Unique dams            : {r['unique_dams']:,}")
    print(
        f"  Career scale           : {FOALS_PER_BROODMARE_LOW}–{FOALS_PER_BROODMARE_HIGH} "
        f"foals × ~{int(LIVE_FOAL_RATE*100)}% live  →  ≈{EXPECTED_LIVE_FOALS:.1f} live foals"
    )
    print("-" * 72)
    if r.get("mean_progeny_price") is not None:
        print(f"  Mean progeny price     : {fmt_money(r['mean_progeny_price'])}")
    if r.get("median_progeny_price") is not None:
        print(f"  Median progeny price   : {fmt_money(r['median_progeny_price'])}")
    if r.get("mean_total_per_dam") is not None:
        print(f"  Mean Σ auction / dam   : {fmt_money(r['mean_total_per_dam'])}")
    if r.get("sum_progeny_auction") is not None:
        print(f"  Σ progeny at auction   : {fmt_money(r['sum_progeny_auction'])}")
    if r.get("mean_added_value_multiplier") is not None:
        print(
            f"  Mean added-value mult  : {r['mean_added_value_multiplier']:.2f}× stud fee"
        )
    if r.get("median_added_value_multiplier") is not None:
        print(
            f"  Median added-value mult: {r['median_added_value_multiplier']:.2f}× stud fee"
        )
    examples = r.get("multiplier_examples") or []
    if examples:
        print("-" * 72)
        print(f"  {'Covering sire':<22} {'Sale':>12} {'Fee':>12} {'Added':>10}")
        for m in examples[:8]:
            print(
                f"  {(m.get('sire') or '?'):<22} {fmt_money(m['price']):>12} "
                f"{fmt_money(m['stud_fee']):>12} {m['multiplier']:>9.2f}×"
            )
    print("-" * 72)
    emp = r.get("empirical_bv")
    proj = r.get("projected_career_bv")
    if emp is not None:
        print(f"  Empirical E[BV] (Σ auction)     : {fmt_money(emp)}")
    if proj is not None:
        print(f"  Projected career E[BV]          : {fmt_money(proj)}")
        print(f"    (= ≈{EXPECTED_LIVE_FOALS:.1f} live foals × median progeny price)")
    print("=" * 72 + "\n")


# ---------------------------------------------------------------------------
# Projected race earnings
# ---------------------------------------------------------------------------
def project_race_earnings(stallion_name: str, verbose: bool = True) -> dict:
    """
    (Earnings / runner) · (runners / # foals with age ≥ 3)

    Equivalent to total_progeny_earnings / foals_of_racing_age when
    earnings/runner is taken from the stallion profile.
    """
    canon, profile = _profile_lookup(stallion_name)
    display = canon or stallion_name.strip()
    used_fallback = False
    fallback_peer = None

    def _from_profile(name: str, prof: dict) -> Optional[dict]:
        prog = prof.get("Progeny Racing Statistics") or {}
        earn = prof.get("Progeny Earnings Statistics") or {}
        runners = prog.get("Starters") or prog.get("Runners")
        foals_ra = prog.get("Foals of Racing Age") or prog.get("Foals")
        avg = parse_money(earn.get("Avg Earnings/starter", 0))
        total = parse_money(earn.get("Earnings", 0))
        try:
            runners_n = int(runners) if runners is not None else 0
        except (TypeError, ValueError):
            runners_n = 0
        try:
            foals_n = int(foals_ra) if foals_ra is not None else 0
        except (TypeError, ValueError):
            foals_n = 0
        if avg <= 0 and total > 0 and runners_n > 0:
            avg = total / runners_n
        if foals_n <= 0 or avg <= 0:
            return None
        runner_rate = runners_n / foals_n if foals_n else 0.0
        projected = avg * runner_rate  # earnings per foal of racing age
        return {
            "earnings_per_runner": avg,
            "runners": runners_n,
            "foals_age_ge_3": foals_n,
            "runners_per_foal": runner_rate,
            "projected_earnings_per_foal": projected,
            "total_progeny_earnings": total if total else avg * runners_n,
        }

    stats = _from_profile(display, profile) if profile else None

    if stats is None:
        used_fallback = True
        for peer_name, peer_prof, _ in similar_isf_peers(display, top_n=10):
            stats = _from_profile(peer_name, peer_prof)
            if stats:
                fallback_peer = peer_name
                break

    result = {
        "kind": "race_earnings",
        "stallion": display,
        "used_similar_isf_fallback": used_fallback and fallback_peer is not None,
        "fallback_peer": fallback_peer,
        **(stats or {}),
        "projected_earnings_per_foal": (stats or {}).get("projected_earnings_per_foal"),
    }

    if verbose:
        print("\n" + "=" * 72)
        print("  VALUE PROJECTOR — PROJECTED RACE EARNINGS")
        print("=" * 72)
        print(f"  Stallion               : {display}")
        if result.get("used_similar_isf_fallback"):
            print(f"  Similar-ISF fallback   : {fallback_peer}")
        if stats:
            print(f"  Earnings / runner      : {fmt_money(stats['earnings_per_runner'])}")
            print(f"  Runners                : {stats['runners']:,}")
            print(f"  Foals age ≥ 3          : {stats['foals_age_ge_3']:,}")
            print(f"  Runners / foal         : {stats['runners_per_foal']:.1%}")
            print("-" * 72)
            print(
                f"  Projected = (E/runner)·(runners/foals≥3) "
                f"= {fmt_money(stats['projected_earnings_per_foal'])} per foal"
            )
        else:
            print("  Insufficient progeny and peer data to project race earnings.")
        print("=" * 72 + "\n")

    return result


def print_bm_sire_timeline() -> None:
    print("\n" + "=" * 72)
    print("  BROODMARE-SIRE DEVELOPMENT TIMELINE")
    print("=" * 72)
    for label, ages in BM_SIRE_TIMELINE:
        print(f"  {label:<32} {ages}")
    print(
        "\n  Grandchildren take ~11–13 years to reach the sales ring — hence the\n"
        "  similar-ISF / familial-bond fallback when that data does not exist yet."
    )
    print("=" * 72 + "\n")


# ---------------------------------------------------------------------------
# Interactive menu
# ---------------------------------------------------------------------------
def run_value_projector_menu() -> None:
    while True:
        print("\n=========================================")
        print("           VALUE PROJECTOR               ")
        print("=========================================")
        print(" [1] Project COLT breeding value (by sire)")
        print(" [2] Project FILLY / MARE breeding value")
        print(" [3] Project race earnings (stallion)")
        print(" [4] Broodmare-sire timeline")
        print(" [B] Back / Exit")
        print("=========================================")
        choice = input("Select an option: ").strip().lower()

        if choice in ("b", "e", "q", ""):
            break

        if choice == "1":
            sire = input("Enter the colt's sire (e.g. Tapit, Flightline): ").strip()
            if sire:
                project_colt_bv(sire, verbose=True)

        elif choice == "2":
            print("  [1] Filly by broodmare-sire lens (e.g. Tapit)")
            print("  [2] Specific mare (sum her progeny auction prices)")
            sub = input("Choose 1 or 2: ").strip()
            name = input("Enter horse name: ").strip()
            if not name:
                continue
            if sub == "2":
                project_filly_bv(name, mode="mare", verbose=True)
            else:
                project_filly_bv(name, mode="bms", verbose=True)

        elif choice == "3":
            name = input("Enter stallion name: ").strip()
            if name:
                project_race_earnings(name, verbose=True)

        elif choice == "4":
            print_bm_sire_timeline()

        else:
            print("Invalid selection.")


if __name__ == "__main__":
    run_value_projector_menu()

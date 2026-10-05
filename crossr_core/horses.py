"""Horse search, profiles, and pedigree trees as JSON."""
import csv
import datetime
import glob
import os
import re

import main
import hypomating_engine

_SEARCH_INDEX = None
_FEE_HISTORY = None
_MARES_HISTORY = None
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def parse_horse_label(raw):
    if not raw:
        return {"name": "UNKNOWN", "year": ""}
    text = str(raw).strip()
    match = re.search(r"(.*?)\s*\((.*?)\)", text)
    if match:
        return {"name": match.group(1).strip(), "year": match.group(2).strip()}
    return {"name": text, "year": ""}


def trim_pedigree(node, depth=0, max_depth=5):
    if not node or not isinstance(node, dict) or depth > max_depth:
        return None
    raw = node.get("Horse", "UNKNOWN")
    parsed = parse_horse_label(raw)
    db_lookup = main.PEDIGREE_DATABASE.get(main.clean_horse_name(raw), {}) if depth < max_depth else {}
    sire = (node.get("Sire") if isinstance(node, dict) else None) or db_lookup.get("Sire")
    dam = (node.get("Dam") if isinstance(node, dict) else None) or db_lookup.get("Dam")
    return {
        "name": parsed["name"],
        "year": parsed["year"],
        "display": raw,
        "key": main.clean_horse_name(raw),
        "sire": trim_pedigree(sire, depth + 1, max_depth) if depth < max_depth else None,
        "dam": trim_pedigree(dam, depth + 1, max_depth) if depth < max_depth else None,
    }


def _format_ratio(ratio_str):
    if not ratio_str or "/" not in str(ratio_str):
        return None
    try:
        parts = str(ratio_str).split("/")
        pct = (int(parts[1]) / int(parts[0])) * 100
        return f"{pct:.1f}% ({parts[1]} foals from {parts[0]} mares)"
    except Exception:
        return str(ratio_str)


def _stud_rank(name):
    clean = main.clean_horse_name(name)
    for idx, r_name in enumerate(hypomating_engine.RAW_RANKING_ORDER, 1):
        if main.clean_horse_name(r_name) == clean:
            return idx
    return None


def crop_label(entered_stud, current_year=None):
    if not entered_stud:
        return None
    try:
        year = int(entered_stud)
    except (TypeError, ValueError):
        return None
    current_year = current_year or datetime.datetime.now().year
    oldest_age = current_year - (year + 1)
    if oldest_age < 0:
        return "First foals upcoming"
    if oldest_age == 0:
        return "First weanlings"
    if oldest_age == 1:
        return "First yearlings"
    if oldest_age == 2:
        return "First-crop sire"
    if oldest_age == 3:
        return "Second-crop sire"
    return "Established"


def stallion_badge(stallion):
    rank = stallion.get("rank")
    crop = stallion.get("crop") or ""
    wins = str(stallion.get("major_wins") or "").lower()
    if rank and rank <= 3:
        return "Leading Sire"
    if "first-crop" in crop.lower() or "yearling" in crop.lower() or "weanling" in crop.lower():
        return "Top Young Sire"
    if "derby" in wins or "triple crown" in wins or "classic" in wins:
        return "Classic Sire"
    if rank and rank <= 15:
        return f"Sire Rank #{rank}"
    return crop


def _fee_num(raw):
    try:
        return int(str(raw).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return 0


def top_progeny_for_sire(sire_name, limit=12):
    payload = hypomating_engine.top_crosses_payload(main.PEDIGREE_DATABASE, sire_name, limit=40)
    rows = []
    for cross in payload.get("crosses", []):
        for w in cross.get("winners", []):
            rows.append({
                "name": w["name"],
                "sex": "",
                "broodmare_sire": cross["broodmare_sire"],
                "class": w["status"],
                "dam": w.get("dam"),
            })
            if len(rows) >= limit:
                return rows
    return rows


def parent_names(search_name):
    tree = main.PEDIGREE_DATABASE.get(main.clean_horse_name(search_name))
    if not tree:
        return None, None
    sire = tree.get("Sire") or {}
    dam = tree.get("Dam") or {}
    sire_name = sire.get("Horse") if isinstance(sire, dict) else sire
    dam_name = dam.get("Horse") if isinstance(dam, dict) else dam
    sire_name = re.sub(r"\s*\(\d{4}\)", "", str(sire_name or "")).strip()
    dam_name = re.sub(r"\s*\(\d{4}\)", "", str(dam_name or "")).strip()
    return sire_name or None, dam_name or None


def list_farms(profiles=None):
    profiles = profiles if profiles is not None else main.load_master_profiles()
    farms = sorted({str(v.get("Farm", "")).replace("_", " ").title() for v in profiles.values() if v.get("Farm")})
    return farms


def list_stallions(
    profiles=None,
    q="",
    sort="rank",
    farm="",
    min_fee=None,
    max_fee=None,
    stud_year_min=None,
    stud_year_max=None,
    crop="",
):
    profiles = profiles if profiles is not None else main.load_master_profiles()
    qn = main.clean_horse_name(q) if q else ""
    farm_n = farm.replace("_", " ").strip().lower() if farm else ""
    rows = []
    for name, data in profiles.items():
        if str(data.get("Status", "")).strip().lower() == "pensioned":
            continue
        if qn and qn not in main.clean_horse_name(name):
            continue
        farm_title = str(data.get("Farm", "")).replace("_", " ").title()
        if farm_n and farm_n not in farm_title.lower():
            continue
        fee = data.get("Stud Fee", 0)
        fee_n = fee if isinstance(fee, int) else _fee_num(fee)
        if min_fee is not None and fee_n < int(min_fee):
            continue
        if max_fee is not None and fee_n > int(max_fee):
            continue
        stud_year = data.get("Stud Duty Year") or 0
        try:
            stud_year = int(stud_year)
        except (TypeError, ValueError):
            stud_year = 0
        if stud_year_min is not None and stud_year < int(stud_year_min):
            continue
        if stud_year_max is not None and stud_year > int(stud_year_max):
            continue
        crop_l = crop_label(stud_year)
        if crop and crop.lower() not in (crop_l or "").lower():
            continue
        rank = _stud_rank(name)
        sire, dam = parent_names(name)
        stallion_meta = {
            "rank": rank,
            "crop": crop_l,
            "major_wins": data.get("Major Wins", ""),
        }
        fee_display = f"${fee_n:,}" if fee_n > 0 else "Private / N/A"
        rows.append({
            "name": name,
            "key": main.clean_horse_name(name),
            "sire": sire,
            "dam": dam,
            "farm": farm_title,
            "stud_fee": fee_display,
            "stud_fee_num": fee_n,
            "year_foaled": data.get("Year Born"),
            "entered_stud": stud_year,
            "rank": rank if rank is not None else 9999,
            "crop": crop_l,
            "badge": stallion_badge(stallion_meta),
            "surface": data.get("Surface", "Both"),
        })
    reverse = False
    keyfn = lambda r: (r["rank"], r["name"])
    if sort == "name":
        keyfn = lambda r: r["name"].lower()
    elif sort == "fee_desc":
        keyfn = lambda r: r["stud_fee_num"]
        reverse = True
    elif sort == "fee_asc":
        keyfn = lambda r: r["stud_fee_num"]
    elif sort == "stud_year":
        keyfn = lambda r: r["entered_stud"] or 0
        reverse = True
    rows.sort(key=keyfn, reverse=reverse)
    if sort == "rank":
        rows.sort(key=lambda r: (r["rank"], r["name"]))
    return rows


def build_search_index(profiles=None):
    global _SEARCH_INDEX
    profiles = profiles if profiles is not None else main.load_master_profiles()
    entries = {}
    for key, tree in main.PEDIGREE_DATABASE.items():
        display = tree.get("Horse", key) if isinstance(tree, dict) else key
        parsed = parse_horse_label(display)
        ck = main.clean_horse_name(key)
        entries[ck] = {
            "key": ck,
            "name": parsed["name"],
            "year": parsed["year"],
            "display": display,
            "has_pedigree": True,
            "has_profile": False,
        }
    for key, data in profiles.items():
        ck = main.clean_horse_name(key)
        year = str(data.get("Year Born", "") or "")
        if ck in entries:
            entries[ck]["has_profile"] = True
            entries[ck]["farm"] = str(data.get("Farm", "")).replace("_", " ").title()
            if year and not entries[ck]["year"]:
                entries[ck]["year"] = year
        else:
            entries[ck] = {
                "key": ck,
                "name": key,
                "year": year,
                "display": key,
                "has_pedigree": False,
                "has_profile": True,
                "farm": str(data.get("Farm", "")).replace("_", " ").title(),
            }
    _SEARCH_INDEX = list(entries.values())
    return _SEARCH_INDEX


def search_horses(query, limit=15, profiles=None):
    q = main.clean_horse_name(query)
    if not q:
        return []
    index = _SEARCH_INDEX if _SEARCH_INDEX is not None else build_search_index(profiles)
    scored = []
    for item in index:
        key = item["key"]
        name = main.clean_horse_name(item["name"])
        if key == q or name == q:
            scored.append((0, item))
        elif key.startswith(q) or name.startswith(q):
            scored.append((1, item))
        elif q in key or q in name:
            scored.append((2, item))
    scored.sort(key=lambda x: (x[0], x[1]["name"]))
    return [item for _, item in scored[:limit]]


def _format_stud_fee(raw):
    text = str(raw or "").strip()
    if not text:
        return None
    if text.lower() == "private":
        return "Private"
    usd = re.match(r"^USD\s*([\d,]+)$", text, re.I)
    if usd:
        return f"${int(usd.group(1).replace(',', '')):,}"
    return text


def _intish(val):
    if val is None or str(val).strip() == "":
        return None
    digits = re.sub(r"[^\d]", "", str(val))
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def load_book_stats():
    """Load historical stud fees and mares-bred rows, keyed by cleaned stallion name."""
    global _FEE_HISTORY, _MARES_HISTORY
    if _FEE_HISTORY is not None and _MARES_HISTORY is not None:
        return _FEE_HISTORY, _MARES_HISTORY

    fees = {}
    fee_path = os.path.join(ROOT, "stud_fee_database.csv")
    if os.path.exists(fee_path):
        with open(fee_path, encoding="utf-8-sig", errors="ignore") as f:
            for row in csv.DictReader(f):
                name = main.clean_horse_name(row.get("Stallion") or "")
                year = _intish(row.get("Year"))
                if not name or not year:
                    continue
                fees.setdefault(name, {})[year] = _format_stud_fee(row.get("Stud Fee"))

    mares = {}
    pattern = os.path.join(ROOT, "live_foal_statistics", "*.csv")
    for path in glob.glob(pattern):
        match = re.search(r"(\d{4}) Breeding Season", os.path.basename(path))
        year = int(match.group(1)) if match else None
        if not year:
            continue
        with open(path, encoding="utf-8-sig", errors="ignore") as f:
            for row in csv.DictReader(f):
                name = main.clean_horse_name(row.get("Stallion") or "")
                if not name:
                    continue
                mares.setdefault(name, {})[year] = {
                    "year": year,
                    "mares_bred": _intish(row.get("Mares Bred")),
                    "live_foals": _intish(row.get("Live Foals")),
                    "live_foal_pct": (row.get("Live Foal %") or "").strip() or None,
                    "state": (row.get("State") or "").strip() or None,
                }

    try:
        import mares_bred_2025_by_stallion as mb_data
        for s in mb_data.mares_bred_database.get("North American Stallions", []):
            name = main.clean_horse_name(s.get("stallion") or "")
            if not name:
                continue
            raw_lf = s.get("live_foal_percentage_for_2025_foals")
            live_foals = None
            live_pct = None
            if raw_lf and "/" in str(raw_lf):
                parts = str(raw_lf).split("/")
                try:
                    reports, foals = int(parts[0]), int(parts[1])
                    live_foals = foals
                    live_pct = f"{(foals / reports) * 100:.0f}%" if reports else None
                except Exception:
                    live_pct = str(raw_lf)
            mares.setdefault(name, {})[2025] = {
                "year": 2025,
                "mares_bred": _intish(s.get("mares_bred_2025")),
                "live_foals": live_foals,
                "live_foal_pct": live_pct,
                "state": s.get("state_prov"),
            }
    except Exception:
        pass

    _FEE_HISTORY = fees
    _MARES_HISTORY = mares
    return fees, mares


def stud_book_history(stallion_name):
    fees, mares = load_book_stats()
    key = main.clean_horse_name(stallion_name)
    fee_years = fees.get(key, {})
    mare_years = mares.get(key, {})
    years = sorted(set(fee_years) | set(mare_years), reverse=True)
    rows = []
    for year in years:
        mb = mare_years.get(year) or {}
        rows.append({
            "year": year,
            "stud_fee": fee_years.get(year),
            "mares_bred": mb.get("mares_bred"),
            "live_foals": mb.get("live_foals"),
            "live_foal_pct": mb.get("live_foal_pct"),
            "state": mb.get("state"),
        })
    return rows


_DAM_INDEX = None
_STAKES_BY_KEY = None
_STATUS_WEIGHT = {"MG1W": 7, "G1W": 6, "MGSW": 5, "G2W": 4, "G3W": 3, "MSW": 2, "SW": 1}


def _sex_letter(sex):
    s = str(sex or "").strip().upper()
    if s.startswith("F") or s.startswith("M"):
        return "f"
    if s.startswith("G"):
        return "g"
    if s.startswith("H") or s.startswith("C") or s.startswith("S"):
        return "c"
    return ""


def _race_labels(records):
    labels = []
    seen = set()
    for rec in records or []:
        name = str(rec.get("Race Name") or "").strip()
        if not name:
            continue
        grade = str(rec.get("Grade") or "").strip().upper()
        year = str(rec.get("Race Year") or "").strip()
        label = name
        if grade:
            label = f"{name} [{grade}]"
        if year:
            label = f"{label} ({year})"
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        labels.append(label)
    return labels


def load_stakes_index():
    global _STAKES_BY_KEY
    if _STAKES_BY_KEY is not None:
        return _STAKES_BY_KEY
    raw = hypomating_engine.load_stakes_data()
    summaries = hypomating_engine.build_horse_summaries(raw)
    grouped = {}
    for rec in raw:
        key = main.clean_horse_name(rec.get("Horse Name") or "")
        if not key:
            continue
        grouped.setdefault(key, []).append(rec)
    by_key = {}
    for key, recs in grouped.items():
        first = recs[0]
        summary = summaries.get(first.get("Horse Name")) or {}
        by_key[key] = {
            "name": first.get("Horse Name") or key,
            "sex": _sex_letter(first.get("Sex") or summary.get("sex")),
            "status": summary.get("status"),
            "races": _race_labels(recs),
        }
    _STAKES_BY_KEY = by_key
    return _STAKES_BY_KEY


def dam_produce_index():
    global _DAM_INDEX
    if _DAM_INDEX is not None:
        return _DAM_INDEX
    idx = {}
    for key, tree in main.PEDIGREE_DATABASE.items():
        if not isinstance(tree, dict):
            continue
        dam = tree.get("Dam")
        dam_raw = dam.get("Horse") if isinstance(dam, dict) else dam
        dam_key = main.clean_horse_name(dam_raw or "")
        if not dam_key:
            continue
        sire = tree.get("Sire")
        sire_raw = sire.get("Horse") if isinstance(sire, dict) else sire
        parsed = parse_horse_label(tree.get("Horse") or key)
        sire_parsed = parse_horse_label(sire_raw or "")
        idx.setdefault(dam_key, []).append({
            "name": parsed["name"],
            "year": parsed["year"],
            "key": main.clean_horse_name(tree.get("Horse") or key),
            "sire": sire_parsed["name"],
        })
    _DAM_INDEX = idx
    return _DAM_INDEX


def _produce_rows(dam_key, subject_key, include_grandkids=True, limit=20):
    stakes = load_stakes_index()
    children = dam_produce_index().get(dam_key) or []
    uniq = {}
    for child in children:
        uniq.setdefault(child["key"], child)
    rows = []
    for child in uniq.values():
        rec = stakes.get(child["key"]) or {}
        grand = []
        if include_grandkids:
            for gk in (dam_produce_index().get(child["key"]) or [])[:8]:
                gk_rec = stakes.get(gk["key"]) or {}
                if not gk_rec.get("status") and not gk_rec.get("races"):
                    continue
                grand.append({
                    "name": gk["name"],
                    "year": gk["year"],
                    "sire": gk["sire"],
                    "sex": gk_rec.get("sex") or "",
                    "status": gk_rec.get("status"),
                    "races": gk_rec.get("races") or [],
                    "is_subject": gk["key"] == subject_key,
                })
        rows.append({
            "name": child["name"],
            "year": child["year"],
            "sire": child["sire"],
            "sex": rec.get("sex") or "",
            "status": rec.get("status"),
            "races": rec.get("races") or [],
            "is_subject": child["key"] == subject_key,
            "produce": grand,
        })
    rows.sort(key=lambda r: (
        0 if r["is_subject"] else 1,
        -_STATUS_WEIGHT.get(r.get("status") or "", 0),
        r["name"].lower(),
    ))
    return rows[:limit]


def female_family(pedigree_data, subject_name=""):
    ordinals = ["1st dam", "2nd dam", "3rd dam", "4th dam"]
    subject_key = main.clean_horse_name(subject_name)
    stakes = load_stakes_index()
    dams = []
    curr = pedigree_data.get("Dam") if isinstance(pedigree_data, dict) else None
    for i in range(4):
        if not curr or not isinstance(curr, dict):
            break
        parsed = parse_horse_label(curr.get("Horse") or "")
        sire_node = curr.get("Sire")
        sire_raw = sire_node.get("Horse") if isinstance(sire_node, dict) else sire_node
        sire_parsed = parse_horse_label(sire_raw or "")
        dam_key = main.clean_horse_name(curr.get("Horse") or "")
        rec = stakes.get(dam_key) or {}
        dams.append({
            "ordinal": ordinals[i],
            "name": parsed["name"],
            "year": parsed["year"],
            "sire": sire_parsed["name"],
            "status": rec.get("status"),
            "racing": rec.get("races") or [],
            "produce": _produce_rows(dam_key, subject_key, include_grandkids=(i == 0)),
        })
        curr = curr.get("Dam")
    return dams


def get_horse_profile(search_name, profiles=None):
    profiles = profiles if profiles is not None else main.load_master_profiles()
    clean_search = main.clean_horse_name(search_name)
    data = None
    matched_key = None
    for key in profiles.keys():
        if main.clean_horse_name(key) == clean_search:
            data = profiles[key]
            matched_key = key
            break

    pedigree_data = main.PEDIGREE_DATABASE.get(clean_search)
    if not pedigree_data:
        for key, tree in main.PEDIGREE_DATABASE.items():
            if main.clean_horse_name(key) == clean_search:
                pedigree_data = tree
                break

    horse_name = matched_key.upper() if matched_key else search_name.strip().upper()
    if pedigree_data and isinstance(pedigree_data, dict) and pedigree_data.get("Horse"):
        horse_name = pedigree_data.get("Horse")

    has_valid_pedigree = False
    if pedigree_data and isinstance(pedigree_data, dict):
        db_lookup = main.PEDIGREE_DATABASE.get(clean_search, {})
        if (
            pedigree_data.get("Sire")
            or db_lookup.get("Sire")
            or pedigree_data.get("Dam")
            or db_lookup.get("Dam")
        ):
            has_valid_pedigree = True

    if not data and not has_valid_pedigree:
        return None

    race_rows = []
    race_totals = {"starts": 0, "firsts": 0, "seconds": 0, "thirds": 0, "earnings": 0}
    stallion = None
    if data:
        current_year = datetime.datetime.now().year
        birth_year = data.get("Year Born", current_year)
        raw_fee = data.get("Stud Fee", 0)
        if isinstance(raw_fee, int) and raw_fee > 0:
            stud_fee_display = f"${raw_fee:,}"
        elif str(raw_fee).strip().upper() == "N/A" or raw_fee == 0:
            stud_fee_display = "Private / N/A"
        else:
            stud_fee_display = str(raw_fee)

        race_record = data.get("Race Record", {}) or {}
        if isinstance(race_record, dict):
            for age_key, stats in race_record.items():
                starts = stats.get("Starts", 0) or 0
                firsts = stats.get("1sts", 0) or 0
                seconds = stats.get("2nds", 0) or 0
                thirds = stats.get("3rds", 0) or 0
                earnings = stats.get("Earnings", 0)
                if stats.get("Season"):
                    estimated_season = stats.get("Season")
                else:
                    age_digits = re.findall(r"\d+", age_key)
                    estimated_season = birth_year + int(age_digits[0]) if age_digits else birth_year
                earn_num = 0
                if isinstance(earnings, (int, float)):
                    earn_num = earnings
                else:
                    clean_earn = re.sub(r"[^\d]", "", str(earnings))
                    if clean_earn.isdigit():
                        earn_num = int(clean_earn)
                race_totals["starts"] += starts
                race_totals["firsts"] += firsts
                race_totals["seconds"] += seconds
                race_totals["thirds"] += thirds
                race_totals["earnings"] += earn_num
                race_rows.append({
                    "season": estimated_season,
                    "age": age_key,
                    "starts": starts,
                    "firsts": firsts,
                    "seconds": seconds,
                    "thirds": thirds,
                    "earnings": earn_num,
                    "earnings_display": f"${earn_num:,}" if earn_num else "$0",
                    "accomplishments": stats.get("Major Accomplishments", "n/a"),
                })

        mares_bred_val = None
        lf_2025_val = None
        lf_2024_val = None
        try:
            import mares_bred_2025_by_stallion as mb_data
            for s in mb_data.mares_bred_database.get("North American Stallions", []):
                if main.clean_horse_name(s.get("stallion", "")) == clean_search:
                    mares_bred_val = s.get("mares_bred_2025")
                    lf_2025_val = _format_ratio(s.get("live_foal_percentage_for_2025_foals"))
                    lf_2024_val = _format_ratio(s.get("live_foal_percentage_for_2024_foals"))
                    break
        except Exception:
            pass

        stallion = {
            "farm": str(data.get("Farm", "Unknown")).replace("_", " ").title(),
            "year_foaled": birth_year,
            "entered_stud": data.get("Stud Duty Year", current_year),
            "stud_fee": stud_fee_display,
            "stud_fee_num": raw_fee if isinstance(raw_fee, int) else 0,
            "surface": data.get("Surface", "Both"),
            "status": data.get("Status", "active"),
            "height": data.get("Height", "N/A"),
            "conformation": data.get("Conformation & Physical Profile", "Information unavailable."),
            "major_wins": data.get("Major Wins", "N/A"),
            "career_highlight": data.get("Career Highlight", "N/A"),
            "rank": _stud_rank(matched_key or search_name),
            "progeny_racing": data.get("Progeny Racing Statistics"),
            "progeny_earnings": data.get("Progeny Earnings Statistics"),
            "legacy_progeny": data.get("Legacy Progeny Stats"),
            "mares_bred_2025": mares_bred_val,
            "live_foal_2025": lf_2025_val,
            "live_foal_2024": lf_2024_val,
        }

    inbreeding = None
    tree = None
    if has_valid_pedigree:
        tree = trim_pedigree(pedigree_data)
        inbreeding = main.compute_inbreeding(pedigree_data)

    parsed = parse_horse_label(horse_name)
    if stallion:
        stallion["crop"] = crop_label(stallion.get("entered_stud"))
        stallion["badge"] = stallion_badge(stallion)
        stallion["sire"] = tree["sire"]["name"] if tree and tree.get("sire") else None
        stallion["dam"] = tree["dam"]["name"] if tree and tree.get("dam") else None
    if has_valid_pedigree or data:
        payload_top = top_progeny_for_sire(clean_search)
    else:
        payload_top = []
    parsed = parse_horse_label(horse_name)
    result = {
        "key": clean_search,
        "name": parsed["name"],
        "year": parsed["year"] or (str(stallion["year_foaled"]) if stallion else ""),
        "display": horse_name,
        "has_profile": data is not None,
        "has_pedigree": has_valid_pedigree,
        "stallion": stallion,
        "race_record": race_rows,
        "race_totals": race_totals,
        "pedigree": tree,
        "inbreeding": inbreeding,
        "top_progeny": payload_top,
        "stud_book": stud_book_history(matched_key or search_name) if data else [],
        "female_family": female_family(pedigree_data, parsed["name"]) if pedigree_data else [],
    }
    return result

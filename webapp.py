"""Sales hub. Reads placeholderdatabase CSVs through the same tables as schema.sql."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import placeholder_store
import sales_health
import upcoming_catalogs

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
SEX_WORDS = {
    "C": "Colt", "F": "Filly", "M": "Mare", "H": "Horse",
    "G": "Gelding", "R": "Ridgling", "W": "Weanling",
}
DAM_RELATIONS = ["first_dam", "second_dam", "third_dam", "fourth_dam", "fifth_dam", "sixth_dam"]
GRADE_SCORE = {"G1": 92, "G2": 76, "G3": 62}

app = FastAPI(title="Sales hub")
app.mount("/assets", StaticFiles(directory=WEB), name="assets")


def _int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _year_text(value: str) -> str:
    match = re.search(r"\d{4}", value or "")
    return match.group(0) if match else (value or "")


def _sex_word(code: str) -> str:
    letter = (code or "").strip().upper()[:1]
    return SEX_WORDS.get(letter, code or "")


def _clients_for(account_id: str):
    clients = [row for row in placeholder_store.load_table("clients") if str(row.get("account_id")) == str(account_id)]
    prefs = placeholder_store.load_table("client_preferences")
    by_client = {row.get("client_id"): row for row in prefs}
    packed = []
    for client in clients:
        preference = by_client.get(client.get("client_id"), {})
        packed.append({**client, "preference": preference})
    return packed


def _stallion_fee(stallion: dict) -> int:
    return _int(stallion.get("stud_fee"))


def hip_matches_preference(hip: dict, preference: dict, stallions: dict) -> bool:
    if not preference:
        return True
    sex = (preference.get("sex") or "").strip().upper()
    if sex and (hip.get("sex") or "").strip().upper()[:1] != sex[:1]:
        return False
    foaled = (preference.get("foaled") or "").strip().upper()
    if foaled and (hip.get("foaled") or "").strip().upper() != foaled:
        return False
    wanted_sire = (preference.get("sire_name") or "").strip()
    if wanted_sire and placeholder_store.name_key(wanted_sire) != placeholder_store.name_key(hip.get("sire") or ""):
        return False
    stallion = stallions.get(placeholder_store.name_key(hip.get("sire") or ""), {})
    surface = (preference.get("surface") or "").strip().lower()
    if surface and (stallion.get("surface") or "").strip().lower() != surface:
        return False
    fee = _stallion_fee(stallion)
    minimum = _int(preference.get("min_stud_fee"))
    if minimum and fee < minimum:
        return False
    maximum = _int(preference.get("max_stud_fee"))
    if maximum and (fee <= 0 or fee > maximum):
        return False
    if str(preference.get("requires_producer_note") or "") == "1":
        if not ((hip.get("dam_success_producer") or "").strip() or (hip.get("cross_success") or "").strip()):
            return False
    return True


def _hip_key(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return str(value or "").strip()
    try:
        return str(int(digits))
    except ValueError:
        return digits


def _catalog_rows(sale_year: str = "", filename: str = "", source_file: str = ""):
    """Upcoming catalogs come from Upcoming Sales/. Placeholder catalog_hips is not the primary source."""
    if filename or source_file:
        rows = upcoming_catalogs.load_catalog_rows(filename=filename, source_file=source_file)
        if sale_year:
            rows = [row for row in rows if str(row.get("sale_year")) == str(sale_year)]
        return rows
    live = []
    for entry in upcoming_catalogs.list_catalog_files():
        if sale_year and str(entry.get("sale_year")) != str(sale_year):
            continue
        live.extend(upcoming_catalogs.load_catalog_rows(filename=entry["filename"]))
    return live


def _lines_for(subject_key: str):
    return [
        row for row in placeholder_store.load_table("pedigree_lines")
        if row.get("subject_key") == subject_key
    ]


def _best_grade(races: list[dict]) -> str:
    order = {"G1": 3, "G2": 2, "G3": 1}
    best = ""
    for race in races:
        grade = (race.get("grade") or "").upper()
        label = "G1" if "G1" in grade else "G2" if "G2" in grade else "G3" if "G3" in grade else ""
        if order.get(label, 0) > order.get(best, 0):
            best = label
    return best


def _money(value) -> str:
    return f"${int(round(value)):,}"


def _crosses(hip: dict):
    sire_key = placeholder_store.name_key(hip.get("sire") or "")
    damsire_key = placeholder_store.name_key(hip.get("sire_of_dam") or "")
    sire_label = hip.get("sire") or "Unknown sire"

    auction = defaultdict(list)
    for row in placeholder_store.load_table("sale_results"):
        if placeholder_store.name_key(row.get("sire") or "") != sire_key:
            continue
        key = placeholder_store.name_key(row.get("sire_of_dam") or "")
        if not key:
            continue
        auction[key].append(row)

    graded = defaultdict(list)
    for row in placeholder_store.load_table("graded_stakes_winners"):
        graded[placeholder_store.name_key(row.get("horse_name") or "")].append(row)

    stakes = defaultdict(list)
    for line_group in _group_lines():
        sire_line = next((
            line for line in line_group
            if line.get("line_side") == "sire" and str(line.get("generation")) == "1" and line.get("relation") == "sire"
        ), None)
        damsire_line = next((
            line for line in line_group
            if line.get("relation") == "damsire" and str(line.get("generation")) == "1"
        ), None)
        if not sire_line or placeholder_store.name_key(sire_line.get("ancestor_name") or "") != sire_key:
            continue
        if not damsire_line:
            continue
        subject_key = line_group[0].get("subject_key")
        races = graded.get(subject_key) or []
        if not races:
            continue
        grade = _best_grade(races)
        stakes[placeholder_store.name_key(damsire_line.get("ancestor_name") or "")].append({
            "name": line_group[0].get("subject_name") or "",
            "grade": grade,
            "sale_type": "Stakes",
            "sale_title": races[0].get("race_name") or "",
            "sale_year": races[0].get("race_year") or "",
            "price": races[0].get("purse") or "",
            "detail": grade,
        })

    def progeny_from_auction(rows):
        packed = []
        for row in rows:
            if str(row.get("is_out")) == "1":
                continue
            packed.append({
                "name": row.get("horse_name") or "",
                "sale_title": row.get("sale_title") or "",
                "sale_year": row.get("sale_year") or "",
                "sale_type": row.get("sold_as") or "Sale",
                "price": row.get("price_raw") or "",
                "hip": row.get("hip") or "",
                "detail": "RNA" if str(row.get("is_rna")) == "1" else row.get("price_raw") or "",
            })
        packed.sort(key=lambda item: _int(re.sub(r"[^\d]", "", item["price"]) or 0), reverse=True)
        return packed[:12]

    def score_for(damsire, auction_rows, stakes_rows):
        grades = {item.get("grade") for item in stakes_rows}
        if "G1" in grades:
            return GRADE_SCORE["G1"]
        if "G2" in grades:
            return GRADE_SCORE["G2"]
        if "G3" in grades:
            return GRADE_SCORE["G3"]
        sold_prices = [
            float(row.get("price_num") or 0)
            for row in auction_rows
            if str(row.get("is_out")) != "1" and str(row.get("is_rna")) != "1" and float(row.get("price_num") or 0) > 0
        ]
        if not sold_prices:
            return 36
        average = sum(sold_prices) / len(sold_prices)
        return max(30, min(58, int(32 + min(average / 100000, 4) * 6)))

    keys = set(auction) | set(stakes)
    crosses = []
    for key in keys:
        auction_rows = auction.get(key, [])
        stakes_rows = stakes.get(key, [])
        label_name = ""
        if auction_rows:
            label_name = auction_rows[0].get("sire_of_dam") or ""
        elif stakes_rows:
            label_name = ""
        if not label_name:
            for line in placeholder_store.load_table("pedigree_lines"):
                if line.get("relation") == "damsire" and placeholder_store.name_key(line.get("ancestor_name") or "") == key:
                    label_name = line.get("ancestor_name") or ""
                    break
        crosses.append({
            "label": f"{sire_label} x {label_name or 'unknown damsire'}",
            "damsire": label_name,
            "exact": bool(damsire_key) and key == damsire_key,
            "score": score_for(key, auction_rows, stakes_rows),
            "auction_progeny": progeny_from_auction(auction_rows),
            "stakes_progeny": stakes_rows[:12],
        })
    crosses.sort(key=lambda item: (not item["exact"], -item["score"]))
    exact = [item for item in crosses if item["exact"]]
    similar = [item for item in crosses if not item["exact"]][:6]
    chosen = exact + similar
    note = (hip.get("cross_success") or "").strip()
    if exact and note:
        exact[0]["catalog_note"] = note
    elif note or (damsire_key and not exact):
        stakes_rows = []
        if note:
            stakes_rows.append({
                "name": note,
                "grade": "",
                "sale_type": "Stakes",
                "sale_title": "Catalog cross note",
                "sale_year": "",
                "price": "",
                "detail": note,
            })
        chosen.insert(0, {
            "label": f"{sire_label} x {hip.get('sire_of_dam') or 'damsire'}",
            "damsire": hip.get("sire_of_dam") or "",
            "exact": True,
            "score": 70 if note else 46,
            "auction_progeny": [],
            "stakes_progeny": stakes_rows,
            "catalog_note": note,
        })
    return chosen


_LINE_CACHE = None


def _group_lines():
    global _LINE_CACHE
    if _LINE_CACHE is None:
        grouped = defaultdict(list)
        for line in placeholder_store.load_table("pedigree_lines"):
            grouped[line.get("subject_key")].append(line)
        _LINE_CACHE = list(grouped.values())
    return _LINE_CACHE


_PEDIGREE_INDEX = None
_CLASS_MAP = None


def _split_horse_label(raw: str):
    text = (raw or "").strip()
    year = ""
    year_match = re.search(r"\((\d{4})\)\s*$", text)
    if year_match:
        year = year_match.group(1)
        text = text[: year_match.start()].strip()
    text = re.sub(r"\s+", " ", text).strip()
    return text, year


def _pedigree_index():
    global _PEDIGREE_INDEX
    if _PEDIGREE_INDEX is None:
        namespace = {}
        exec((ROOT / "pedigrees_database.py").read_text(encoding="utf-8"), namespace)
        index = {}
        for key, value in (namespace.get("pedigree_map") or {}).items():
            index[placeholder_store.name_key(str(key))] = value
        _PEDIGREE_INDEX = index
    return _PEDIGREE_INDEX


def _class_map():
    global _CLASS_MAP
    if _CLASS_MAP is None:
        rank = {"": 0, "SW": 1, "G3": 2, "G2": 3, "G1": 4}
        classes = {}
        for row in placeholder_store.load_table("graded_stakes_winners"):
            key = placeholder_store.name_key(row.get("horse_name") or "")
            grade = (row.get("grade") or "").upper()
            label = "G1" if "G1" in grade else "G2" if "G2" in grade else "G3" if "G3" in grade else "SW"
            if rank.get(label, 0) > rank.get(classes.get(key, ""), 0):
                classes[key] = label
        for row in placeholder_store.load_table("stallion_stats"):
            key = placeholder_store.name_key(row.get("stallion_name") or "")
            wins = (row.get("major_wins") or "").upper()
            label = "G1" if "G1" in wins else "G2" if "G2" in wins else "G3" if "G3" in wins else ""
            if label and rank.get(label, 0) > rank.get(classes.get(key, ""), 0):
                classes[key] = label
        _CLASS_MAP = classes
    return _CLASS_MAP


def _class_of(name: str) -> str:
    return _class_map().get(placeholder_store.name_key(name), "")


def _node_for(name: str):
    if not name:
        return None
    return _pedigree_index().get(placeholder_store.name_key(name))


def _pedigree_from_parents(sire_name: str, dam_name: str, sire_of_dam: str = ""):
    """Build sire/dam lines from pedigrees_database, always seeding from the catalog row.

    Even when the yearling itself is missing from pedigrees_database, the Upcoming
    Sales CSV supplies SIRE, DAM, and SIRE OF DAM so the pedigree panel is usable.
    """
    sire_line = []
    # Always start with the catalog sire, then walk his sire line when known.
    if sire_name:
        sire_node = _node_for(sire_name)
        sire_year = ""
        if isinstance(sire_node, dict):
            _, sire_year = _split_horse_label(sire_node.get("Horse", ""))
        sire_line.append({
            "name": sire_name,
            "year": sire_year,
            "class_label": _class_of(sire_name),
            "generation": 1,
        })
        node = sire_node.get("Sire") if isinstance(sire_node, dict) and isinstance(sire_node.get("Sire"), dict) else None
        generation = 2
        while isinstance(node, dict) and generation <= 5:
            name, year = _split_horse_label(node.get("Horse", ""))
            if not name:
                break
            sire_line.append({
                "name": name,
                "year": year,
                "class_label": _class_of(name),
                "generation": generation,
            })
            node = node.get("Sire") if isinstance(node.get("Sire"), dict) else None
            generation += 1

    dams = []
    if dam_name:
        dam_node = _node_for(dam_name)
        dam_year = ""
        damsire_name = sire_of_dam or ""
        if isinstance(dam_node, dict):
            _, dam_year = _split_horse_label(dam_node.get("Horse", ""))
            sire_node = dam_node.get("Sire") if isinstance(dam_node.get("Sire"), dict) else None
            if sire_node:
                from_db, _ = _split_horse_label(sire_node.get("Horse", ""))
                if from_db:
                    damsire_name = from_db
        dams.append({
            "generation": 1,
            "relation": DAM_RELATIONS[0],
            "name": dam_name,
            "year": dam_year,
            "class_label": _class_of(dam_name),
            "damsire": damsire_name,
            "damsire_class": _class_of(damsire_name) if damsire_name else "",
        })
        node = dam_node.get("Dam") if isinstance(dam_node, dict) and isinstance(dam_node.get("Dam"), dict) else None
        generation = 2
        while isinstance(node, dict) and generation <= 6:
            name, year = _split_horse_label(node.get("Horse", ""))
            if not name:
                break
            sire_node = node.get("Sire") if isinstance(node.get("Sire"), dict) else None
            next_damsire, _ = _split_horse_label((sire_node or {}).get("Horse", ""))
            dams.append({
                "generation": generation,
                "relation": DAM_RELATIONS[generation - 1],
                "name": name,
                "year": year,
                "class_label": _class_of(name),
                "damsire": next_damsire,
                "damsire_class": _class_of(next_damsire) if next_damsire else "",
            })
            node = node.get("Dam") if isinstance(node.get("Dam"), dict) else None
            generation += 1
    return {"sire_line": sire_line, "dams": dams}


def _pedigree_block(subject_key: str, sire_name: str = "", dam_name: str = "", sire_of_dam: str = ""):
    lines = _lines_for(subject_key)
    sire_line = [
        line for line in lines
        if line.get("line_side") == "sire" and line.get("relation") == "sire"
    ]
    sire_line.sort(key=lambda line: _int(line.get("generation")))
    dams = []
    for relation in DAM_RELATIONS:
        dam = next((line for line in lines if line.get("relation") == relation), None)
        if not dam:
            continue
        generation = str(dam.get("generation"))
        damsire = next((
            line for line in lines
            if line.get("relation") == "damsire" and str(line.get("generation")) == generation
        ), None)
        dams.append({
            "generation": _int(generation),
            "relation": relation,
            "name": dam.get("ancestor_name") or "",
            "year": dam.get("ancestor_year") or "",
            "class_label": dam.get("class_label") or "",
            "damsire": "" if not damsire else damsire.get("ancestor_name") or "",
            "damsire_class": "" if not damsire else damsire.get("class_label") or "",
        })
    packed = {
        "sire_line": [
            {
                "name": line.get("ancestor_name") or "",
                "year": line.get("ancestor_year") or "",
                "class_label": line.get("class_label") or "",
                "generation": _int(line.get("generation")),
            }
            for line in sire_line
        ],
        "dams": dams,
    }
    # Prefer live catalog parents whenever the CSV supplies them so yearlings
    # missing from pedigrees_database still show sire, dam, and broodmare sire.
    if sire_name or dam_name:
        live = _pedigree_from_parents(sire_name, dam_name, sire_of_dam)
        if live["sire_line"] or live["dams"]:
            # Keep deeper cached dam generations when the live walk is short.
            if len(live["dams"]) < len(packed["dams"]):
                live["dams"] = packed["dams"]
            if len(live["sire_line"]) < len(packed["sire_line"]) and not sire_name:
                live["sire_line"] = packed["sire_line"]
            return live
    return packed


def _family_more(hip: dict, dams: list[dict]):
    first = dams[0]["name"] if dams else hip.get("dam") or ""
    first_key = placeholder_store.name_key(first)
    siblings = []
    for other in _catalog_rows():
        if other.get("hip") == hip.get("hip") and str(other.get("sale_year")) == str(hip.get("sale_year")):
            continue
        if placeholder_store.name_key(other.get("dam") or "") == first_key and first_key:
            siblings.append({
                "hip": other.get("hip"),
                "sale_year": other.get("sale_year"),
                "name": other.get("horse_name"),
                "sire": other.get("sire"),
                "sale_type": other.get("sold_as") or "",
            })
    produce = []
    for horse in placeholder_store.load_table("horses"):
        if placeholder_store.name_key(horse.get("dam_name") or "") != first_key or not first_key:
            continue
        if placeholder_store.name_key(horse.get("name") or "") == placeholder_store.name_key(hip.get("horse_name") or ""):
            continue
        produce.append({
            "name": horse.get("name") or "",
            "year": horse.get("foaling_year") or "",
            "class_label": horse.get("class_label") or "",
            "sire": horse.get("sire_name") or "",
        })
        if len(produce) >= 12:
            break
    return {"further_dams": dams[4:], "siblings": siblings[:12], "produce": produce}


def _note_for(account_id: str, sale_title: str, hip: str):
    matches = [
        row for row in placeholder_store.load_table("notes")
        if str(row.get("account_id")) == str(account_id)
        and row.get("sale_title") == sale_title
        and str(row.get("hip")) == str(hip)
    ]
    if not matches:
        return None
    return matches[-1]


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/bootstrap")
def bootstrap(account_id: str = "1"):
    accounts = placeholder_store.load_table("accounts")
    account = next((row for row in accounts if str(row.get("account_id")) == str(account_id)), accounts[0] if accounts else None)
    editions = placeholder_store.result_sale_editions()
    years = sorted({row["sale_year"] for row in editions if row["sale_year"]}, reverse=True)
    upcoming = upcoming_catalogs.catalog_summary()
    return {
        "roles": placeholder_store.load_table("industry_roles"),
        "account": account,
        "clients": _clients_for(account.get("account_id") if account else account_id),
        "upcoming": upcoming,
        "upcoming_folder": "Upcoming Sales/",
        "upcoming_empty": len(upcoming) == 0,
        "result_sales": editions,
        "result_years": years,
        "result_sale_count": len(editions),
        "catalog_source": "Upcoming Sales/",
    }


@app.get("/api/result-sales")
def result_sales(year: str = "", q: str = "", company: str = ""):
    editions = placeholder_store.result_sale_editions()
    needle = (q or "").strip().lower()
    company_needle = (company or "").strip().lower()
    filtered = []
    for row in editions:
        if year and str(row.get("sale_year")) != str(year):
            continue
        if company_needle and company_needle not in (row.get("sale_company") or "").lower():
            continue
        if needle and needle not in (row.get("sale_title") or "").lower():
            continue
        filtered.append(row)
    years = sorted({row["sale_year"] for row in editions if row["sale_year"]}, reverse=True)
    return {
        "sales": filtered,
        "count": len(filtered),
        "total": len(editions),
        "years": years,
    }


def _price_display(row: dict) -> str:
    if str(row.get("is_out") or "").strip() in {"1", "true", "True"}:
        return "OUT"
    if str(row.get("is_rna") or "").strip() in {"1", "true", "True"}:
        return "RNA"
    raw = (row.get("price_raw") or "").strip()
    try:
        price = float(row.get("price_num") or 0)
    except (TypeError, ValueError):
        price = 0.0
    if price > 0:
        return _money(price)
    return raw or "—"


@app.get("/api/stats")
def stats(sale_title: str, sale_year: str = ""):
    report = sales_health.build_sale_health_report(sale_title)
    if not report:
        raise HTTPException(status_code=404, detail="No sale_results for that sale")
    def round_row(row):
        packed = dict(row)
        for key in ("gross", "average", "median", "sold_pct"):
            if isinstance(packed.get(key), float):
                packed[key] = round(packed[key], 1) if key == "sold_pct" else round(packed[key], 2)
        for key in ("offered_yoy", "gross_yoy", "average_yoy", "median_yoy", "millionaires_yoy"):
            if isinstance(packed.get(key), float):
                packed[key] = round(packed[key], 1)
        packed["gross_display"] = _money(row["gross"])
        packed["average_display"] = _money(row["average"])
        packed["median_display"] = _money(row["median"])
        return packed

    rows = [round_row(row) for row in report["rows"]]
    selected = None
    if sale_year:
        selected = next((row for row in rows if str(row["year"]) == str(sale_year)), None)
    focus = selected or rows[-1]
    # Growth vs prior edition for the focused year (not always the latest year).
    growth = focus.get("average_yoy")
    previous_year = None
    focus_index = next((index for index, row in enumerate(rows) if str(row["year"]) == str(focus["year"])), len(rows) - 1)
    if focus_index > 0:
        previous_year = rows[focus_index - 1]["year"]
    highs = {}
    for name, peak in report["highs"].items():
        value = peak["value"]
        if name in {"highest_gross", "highest_average", "highest_median"}:
            display = _money(value)
        else:
            display = f"{int(value):,}"
        highs[name] = {"year": peak["year"], "display": display}
    return {
        "sale_title": report["sale_title"],
        "sale_year": str(focus["year"]),
        "latest": focus,
        "previous_year": previous_year,
        "growth_vs_previous": None if growth is None else round(growth, 1),
        "rows": rows,
        "highs": highs,
    }


@app.get("/api/sale-hips")
def sale_hips(sale_title: str, sale_year: str):
    if not sale_title or not sale_year:
        raise HTTPException(status_code=400, detail="sale_title and sale_year are required")
    rows = placeholder_store.sale_results_matching(sale_title, sale_year)
    if not rows:
        raise HTTPException(status_code=404, detail="No hips for that sale year")
    hips = []
    for row in rows:
        hips.append({
            "hip": row.get("hip") or "",
            "horse_name": row.get("horse_name") or "",
            "sex": _sex_word(row.get("sex") or ""),
            "sire": row.get("sire") or "",
            "dam": row.get("dam") or "",
            "color": row.get("color") or "",
            "consignor": row.get("consignor") or "",
            "purchaser": row.get("purchaser") or "",
            "price_num": row.get("price_num") or "",
            "price_display": _price_display(row),
            "is_rna": str(row.get("is_rna") or ""),
            "is_out": str(row.get("is_out") or ""),
            "foaled": row.get("foaled") or "",
            "sold_as": row.get("sold_as") or "",
        })
    hips.sort(key=lambda item: _int(re.sub(r"\D", "", item["hip"]) or 0))
    return {
        "sale_title": sale_title,
        "sale_year": str(sale_year),
        "hips": hips,
        "count": len(hips),
    }


@app.get("/api/catalog")
def catalog(
    sale_year: str = "",
    filename: str = "",
    source_file: str = "",
    account_id: str = "1",
    client_id: str = "",
    sex: str = "",
    foaled: str = "",
    sire: str = "",
    surface: str = "",
    min_fee: str = "",
    max_fee: str = "",
):
    stallions = placeholder_store.stallion_index()
    clients = _clients_for(account_id)
    preferences = [client["preference"] for client in clients if client.get("preference")]
    selected = next((client["preference"] for client in clients if str(client.get("client_id")) == str(client_id)), None)
    manual = {
        "sex": sex, "foaled": foaled, "sire_name": sire, "surface": surface,
        "min_stud_fee": min_fee, "max_stud_fee": max_fee,
    }
    hips = []
    for hip in _catalog_rows(sale_year=sale_year, filename=filename, source_file=source_file):
        fits = [hip_matches_preference(hip, preference, stallions) for preference in preferences]
        fits_any = any(fits) if fits else False
        fits_selected = True if not selected else hip_matches_preference(hip, selected, stallions)
        fits_manual = hip_matches_preference(hip, manual, stallions)
        if client_id and not fits_selected:
            continue
        if not fits_manual:
            continue
        hips.append({
            "hip_id": hip.get("hip_id"),
            "hip": hip.get("hip"),
            "sale_year": hip.get("sale_year"),
            "sale_title": hip.get("sale_title"),
            "horse_name": hip.get("horse_name"),
            "sex": hip.get("sex"),
            "sex_word": _sex_word(hip.get("sex") or ""),
            "sire": hip.get("sire"),
            "dam": hip.get("dam"),
            "foaled": hip.get("foaled"),
            "year_of_birth": hip.get("year_of_birth"),
            "starred": hip.get("starred"),
            "fits_any_client": fits_any,
            "sold_as": hip.get("sold_as"),
            "filename": hip.get("filename") or filename,
            "source_file": hip.get("source_file") or source_file,
        })
    hips.sort(key=lambda item: _int(item["hip"]))
    return {
        "hips": hips,
        "count": len(hips),
        "source": "Upcoming Sales/",
        "empty_folder": len(upcoming_catalogs.list_catalog_files()) == 0,
    }


@app.get("/api/hip")
def hip_detail(
    sale_year: str = "",
    hip: str = "",
    account_id: str = "1",
    filename: str = "",
    source_file: str = "",
):
    target = _hip_key(hip)
    match = next((
        row for row in _catalog_rows(sale_year=sale_year, filename=filename, source_file=source_file)
        if _hip_key(row.get("hip") or "") == target
    ), None)
    if not match:
        raise HTTPException(status_code=404, detail="Hip not in catalog. Drop a CSV into Upcoming Sales/.")
    subject_key = placeholder_store.name_key(match.get("horse_name") or "")
    pedigree = _pedigree_block(
        subject_key,
        sire_name=match.get("sire") or "",
        dam_name=match.get("dam") or "",
        sire_of_dam=match.get("sire_of_dam") or "",
    )
    note = _note_for(account_id, match.get("sale_title") or "", match.get("hip") or "")
    return {
        "hip": match.get("hip"),
        "sale_title": match.get("sale_title"),
        "sale_year": match.get("sale_year"),
        "horse_name": match.get("horse_name"),
        "filename": match.get("filename") or filename,
        "source_file": match.get("source_file") or source_file,
        "header": {
            "foaled": match.get("foaled") or "",
            "color": match.get("color") or "",
            "sex": _sex_word(match.get("sex") or ""),
            "year": _year_text(match.get("year_of_birth") or ""),
            "hip": match.get("hip") or "",
            "consignor": match.get("consignor") or "",
            "barn": match.get("barn") or "",
        },
        "sire": match.get("sire") or "",
        "dam": match.get("dam") or "",
        "sire_of_dam": match.get("sire_of_dam") or "",
        "sold_as": match.get("sold_as") or "",
        "pedigree": {
            "sire_line": pedigree["sire_line"],
            "dams": pedigree["dams"][:4],
        },
        "family_more": _family_more(match, pedigree["dams"]),
        "dam_success_producer": match.get("dam_success_producer") or "",
        "dam_success_racer": match.get("dam_success_racer") or "",
        "crosses": _crosses(match),
        "projected_value": None,
        "physical": None,
        "catalog_note": match.get("notes") or "",
        "note": note,
        "source_file": match.get("source_file") or "",
    }


@app.get("/api/horse")
def horse(name: str):
    key = placeholder_store.name_key(name)
    horses = placeholder_store.load_table("horses")
    found = next((row for row in horses if row.get("name_key") == key), None)
    stallions = placeholder_store.stallion_index()
    stallion = stallions.get(key, {})
    pedigree = _pedigree_block(key)
    if not found and not stallion and not pedigree["sire_line"] and not pedigree["dams"]:
        found = {"name": name, "name_key": key, "display_name": name}
    display = (found or {}).get("display_name") or name
    return {
        "name": (found or {}).get("name") or stallion.get("stallion_name") or name,
        "display_name": display,
        "foaling_year": (found or {}).get("foaling_year") or stallion.get("year_born") or "",
        "sex": _sex_word((found or {}).get("sex") or ""),
        "color": (found or {}).get("color") or "",
        "country": (found or {}).get("country") or "",
        "class_label": (found or {}).get("class_label") or "",
        "sire_name": (found or {}).get("sire_name") or "",
        "dam_name": (found or {}).get("dam_name") or "",
        "farm": stallion.get("farm") or "",
        "stud_fee": stallion.get("stud_fee") or "",
        "surface": stallion.get("surface") or "",
        "height": stallion.get("height") or (found or {}).get("height") or "",
        "conformation": stallion.get("conformation") or (found or {}).get("conformation") or "",
        "major_wins": stallion.get("major_wins") or "",
        "career_highlight": stallion.get("career_highlight") or "",
        "pedigree": {
            "sire_line": pedigree["sire_line"],
            "dams": pedigree["dams"][:4],
        },
        "family_more": {"further_dams": pedigree["dams"][4:], "siblings": [], "produce": []},
    }


@app.post("/api/accounts")
def create_account(payload: dict):
    role = (payload.get("industry_role") or "").strip()
    roles = {row.get("role_name") for row in placeholder_store.load_table("industry_roles")}
    if role not in roles:
        raise HTTPException(status_code=400, detail="Choose a role in the industry")
    name = (payload.get("display_name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    rows = placeholder_store.load_table("accounts")
    account_id = placeholder_store.next_id("accounts", "account_id")
    account = {
        "account_id": account_id,
        "display_name": name,
        "email": (payload.get("email") or "").strip(),
        "industry_role": role,
        "created_at": datetime.now(timezone.utc).date().isoformat(),
    }
    rows.append(account)
    placeholder_store.write_table("accounts", rows)
    return {"account": account, "clients": []}


@app.post("/api/clients")
def create_client(payload: dict):
    account_id = str(payload.get("account_id") or "")
    accounts = placeholder_store.load_table("accounts")
    account = next((row for row in accounts if str(row.get("account_id")) == account_id), None)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if account.get("industry_role") != "Bloodstock Agent":
        raise HTTPException(status_code=400, detail="Only a bloodstock agent can add clients")
    client_name = (payload.get("client_name") or "").strip()
    if not client_name:
        raise HTTPException(status_code=400, detail="Client name is required")
    clients = placeholder_store.load_table("clients")
    preferences = placeholder_store.load_table("client_preferences")
    client_id = placeholder_store.next_id("clients", "client_id")
    preference_id = placeholder_store.next_id("client_preferences", "preference_id")
    client = {"client_id": client_id, "account_id": account_id, "client_name": client_name}
    preference = {
        "preference_id": preference_id,
        "client_id": client_id,
        "sex": (payload.get("sex") or "").strip().upper(),
        "foaled": (payload.get("foaled") or "").strip().upper(),
        "surface": (payload.get("surface") or "").strip(),
        "min_stud_fee": payload.get("min_stud_fee") or "",
        "max_stud_fee": payload.get("max_stud_fee") or "",
        "sire_name": (payload.get("sire_name") or "").strip(),
        "requires_producer_note": 1 if payload.get("requires_producer_note") else 0,
    }
    clients.append(client)
    preferences.append(preference)
    placeholder_store.write_table("clients", clients)
    placeholder_store.write_table("client_preferences", preferences)
    return {"client": {**client, "preference": preference}}


@app.post("/api/notes")
def save_note(payload: dict):
    account_id = str(payload.get("account_id") or "1")
    sale_title = payload.get("sale_title") or ""
    hip = str(payload.get("hip") or "")
    body = payload.get("body") if payload.get("body") is not None else ""
    source = payload.get("source") or "typed"
    if source not in {"typed", "voice"}:
        source = "typed"
    rows = placeholder_store.load_table("notes")
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    existing = next((
        row for row in rows
        if str(row.get("account_id")) == account_id and row.get("sale_title") == sale_title and str(row.get("hip")) == hip
    ), None)
    if existing:
        existing["body"] = body
        existing["source"] = source
        existing["updated_at"] = now
        saved = existing
    else:
        saved = {
            "note_id": placeholder_store.next_id("notes", "note_id"),
            "account_id": account_id,
            "sale_title": sale_title,
            "hip": hip,
            "body": body,
            "source": source,
            "updated_at": now,
        }
        rows.append(saved)
    placeholder_store.write_table("notes", rows)
    return {"note": saved}

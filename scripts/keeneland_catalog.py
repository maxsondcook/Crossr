"""Build an Upcoming Sales catalog CSV from Keeneland's online catalog data.

Keeneland's catalog table (keeneland.com/sales/<year>/<id>/<name>/catalog-table/)
loads every hip from a public JSON file:
    https://catalog-backend.keeneland.com/sites/default/files/json_hde/sale_data_<N>.json
which has book, session, color, broodmare sire, foaling date and state,
pregnancy status, covering sire, out/supplement flags and, after the sale,
price and buyer. The table's CSV export only has a few of those columns.

Usage:
    python3 scripts/keeneland_catalog.py SALE_DATA_URL_OR_FILE "Sale Title (2026)" \
        [--extra supplements.json] [--out "Upcoming Sales/Sale Title (2026).csv"]

--extra adds hips the JSON doesn't carry yet (late supplements), as a list of
{hip, name, book, session, sex, state, sold_as, color, sire, dam, damsire,
pregnant, cover, consignor, dob, barn}.
Then publish with:  python3 scripts/load_railway.py --only catalogs
"""

from __future__ import annotations

import argparse
import csv
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COLUMNS = [
    "SALE TITLE", "BOOK", "SESSION", "HIP", "COLOR", "NAME", "SEX", "SIRE", "DAM",
    "SIRE OF DAM", "PROPERTY LINE", "PURCHASER", "PRICE", "RNA", "PRIVATE SALE",
    "YEAR OF BIRTH", "FOALED", "BARN", "COVERING SIRE", "COVER DATE", "PREGNANT",
    "SOLD AS CODE", "SOLD AS DESCRIPTION", "OUT", "SUPPLEMENT",
    "BREEDERS CUP ELIGIBLE", "PEDIGREE PDF", "VIRTUAL INSPECTION", "STARRED",
]


def _load(src: str) -> dict:
    if src.startswith("http"):
        req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.load(resp)
    return json.loads(Path(src).read_text())


def _clean(value) -> str:
    return " ".join(str(value or "").split())


def _name(title: str) -> str:
    # Unnamed weanlings/foals come through as "Hip 0001"; the app then shows "Sire x Dam".
    title = _clean(title)
    return "" if title.lower().startswith("hip ") else title


def rows_from_json(data: dict, title: str) -> list[dict]:
    rows = []
    for r in data.values():
        if _clean(r.get("field_hidden_indicator")) == "Y":
            continue
        hip = _clean(r.get("field_hip_number")) + _clean(r.get("field_hip_alpha"))
        price = _clean(r.get("field_sale_price") or r.get("field_price") or r.get("field_hammer_price"))
        rows.append({
            "SALE TITLE": title,
            "BOOK": _clean(r.get("field_book")),
            "SESSION": _clean(r.get("field_session")),
            "HIP": hip,
            "COLOR": _clean(r.get("field_color")),
            "NAME": _name(r.get("title")),
            "SEX": _clean(r.get("field_sex")),
            "SIRE": _clean(r.get("field_sire")),
            "DAM": _clean(r.get("field_dam")),
            "SIRE OF DAM": _clean(r.get("field_broodmare_sire")),
            "PROPERTY LINE": _clean(r.get("field_consignor")),
            "PURCHASER": _clean(r.get("field_buyer_name") or r.get("field_buyer")),
            "PRICE": price,
            "RNA": _clean(r.get("field_rna_indicator")),
            "YEAR OF BIRTH": _clean(r.get("field_foaling_date") or r.get("field_dob")),
            "FOALED": _clean(r.get("field_foaling_area")),
            "BARN": _clean(r.get("field_barn_text")),
            "COVERING SIRE": _clean(r.get("field_covering_sire")),
            "PREGNANT": _clean(r.get("field_breeding_status")),
            "SOLD AS DESCRIPTION": _clean(r.get("field_sold_as")),
            "OUT": _clean(r.get("field_out")),
            "SUPPLEMENT": _clean(r.get("field_supplement_indicator")),
            "BREEDERS CUP ELIGIBLE": _clean(r.get("field_breeders_cup_eligible")),
            "PEDIGREE PDF": _clean(r.get("field_pedigree")),
        })
    return rows


def rows_from_extra(extra: list[dict], title: str) -> list[dict]:
    return [{
        "SALE TITLE": title, "BOOK": e.get("book", ""), "SESSION": e.get("session", ""),
        "HIP": e["hip"], "COLOR": e.get("color", ""), "NAME": e.get("name", ""),
        "SEX": e.get("sex", ""), "SIRE": e.get("sire", ""), "DAM": e.get("dam", ""),
        "SIRE OF DAM": e.get("damsire", ""), "PROPERTY LINE": e.get("consignor", ""),
        "YEAR OF BIRTH": e.get("dob", ""), "FOALED": e.get("state", ""), "BARN": e.get("barn", ""),
        "COVERING SIRE": e.get("cover", ""), "PREGNANT": e.get("pregnant", ""),
        "SOLD AS DESCRIPTION": e.get("sold_as", ""), "OUT": "N", "SUPPLEMENT": "Y",
    } for e in extra]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="sale_data_<N>.json URL or local file")
    ap.add_argument("title", help='catalog title, e.g. "Keeneland November Breeding Stock Sale (2026)"')
    ap.add_argument("--extra", help="JSON list of hips missing from the source (late supplements)")
    ap.add_argument("--out", help="output CSV (default: Upcoming Sales/<title>.csv)")
    args = ap.parse_args()

    rows = rows_from_json(_load(args.source), args.title)
    if args.extra:
        have = {r["HIP"] for r in rows}
        rows += [r for r in rows_from_extra(json.loads(Path(args.extra).read_text()), args.title) if r["HIP"] not in have]
    rows.sort(key=lambda r: (int("".join(ch for ch in r["HIP"] if ch.isdigit()) or 0), r["HIP"]))

    out = Path(args.out) if args.out else ROOT / "Upcoming Sales" / f"{args.title}.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in COLUMNS})
    print(f"{len(rows)} hips -> {out}")


if __name__ == "__main__":
    main()

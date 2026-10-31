"""Load race entries from a CSV into race_entries (Phase 7 weekly entries).

The CSV comes from a source we are permitted to use (a licensed feed export, a
track's published overnight, or entries typed in); DRF and Equibase entry pages
are not scraped (bot protection). Columns, case-insensitive:

    race_date (YYYY-MM-DD), track_code, race_number, horse   required
    track, country, horse_refno, foal_year, race_type, race_name, distance,
    surface, post_position, status (entered/scratched), source_id    optional

Each horse is linked to race_horses by Equibase refno, else by name when exactly
one non-merged horse has that name (and foal year, if given). Unmatched horses
keep their entry (horse_id empty) and are re-matched on every import, so a
missing pedigree never holds up the weekly list. Re-importing the same race
updates it in place (key: race date, track, race number, horse).

Usage:
    python3 scripts/import_entries.py entries.csv --source "my-feed"           # dry run
    python3 scripts/import_entries.py entries.csv --source "my-feed" --apply
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crossr_core import railway_db, weekly  # noqa: E402

REQUIRED = ("race_date", "track_code", "race_number", "horse")
OPTIONAL = ("track", "country", "horse_refno", "foal_year", "race_type", "race_name", "distance", "surface",
            "post_position", "status", "source_id")


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        heads = {h.strip().lower(): h for h in reader.fieldnames or []}
        missing = [c for c in REQUIRED if c not in heads]
        if missing:
            raise SystemExit(f"missing column(s): {', '.join(missing)}")
        out = []
        for raw in reader:
            row = {c: (raw.get(heads[c]) or "").strip() for c in REQUIRED + OPTIONAL if c in heads}
            if all(row.get(c) for c in REQUIRED):
                row["horse_key"] = weekly.name_key(row["horse"])
                row["race_number"] = int(row["race_number"])
                row["status"] = (row.get("status") or "entered").lower()
                out.append(row)
        return out


def match(conn, row: dict) -> str | None:
    if row.get("horse_refno"):
        hit = conn.execute("SELECT id FROM race_horses WHERE equibase_refno = %s AND coalesce(status, '') <> 'merged'",
                           (row["horse_refno"],)).fetchall()
        if len(hit) == 1:
            return hit[0][0]
    hits = conn.execute(
        """SELECT id, substring(foal_year from '^[0-9]{4}') FROM race_horses
           WHERE name_key = %s AND coalesce(status, '') <> 'merged'""", (row["horse_key"],)).fetchall()
    if row.get("foal_year"):
        hits = [h for h in hits if h[1] in (None, row["foal_year"][:4])]
    return hits[0][0] if len(hits) == 1 else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--source", required=True, help="where the entries came from (stored on each row)")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    rows = read_rows(args.csv)
    with railway_db.connect() as conn:
        conn.execute(weekly.SCHEMA)
        unmatched = []
        for r in rows:
            r["horse_id"] = match(conn, r)
            if not r["horse_id"]:
                unmatched.append(r["horse"])
        print(f"{len(rows)} entries, {len(rows) - len(unmatched)} linked to a horse record, {len(unmatched)} not yet")
        for name in sorted(set(unmatched))[:30]:
            print("  not in database yet:", name)
        if not args.apply:
            conn.rollback()
            print("dry run: nothing written (use --apply)")
            return
        for r in rows:
            conn.execute(
                """INSERT INTO race_entries (source, source_id, race_date, track_code, track, country, race_number,
                       horse_name, horse_key, horse_refno, horse_id, race_type, race_name, distance, surface,
                       post_position, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (race_date, track_code, race_number, horse_key) DO UPDATE SET
                       source = EXCLUDED.source, source_id = EXCLUDED.source_id, track = EXCLUDED.track,
                       horse_id = coalesce(EXCLUDED.horse_id, race_entries.horse_id),
                       race_type = EXCLUDED.race_type, race_name = EXCLUDED.race_name, distance = EXCLUDED.distance,
                       surface = EXCLUDED.surface, post_position = EXCLUDED.post_position,
                       status = EXCLUDED.status, fetched_at = now()""",
                (args.source, r.get("source_id") or None, r["race_date"], r["track_code"].upper(), r.get("track") or None,
                 r.get("country") or None, r["race_number"], r["horse"], r["horse_key"], r.get("horse_refno") or None,
                 r["horse_id"], r.get("race_type") or None, r.get("race_name") or None, r.get("distance") or None,
                 r.get("surface") or None, r.get("post_position") or None, r["status"]))
        # earlier entries whose horse has since been scraped
        relinked = conn.execute(
            """UPDATE race_entries e SET horse_id = h.id FROM race_horses h
               WHERE e.horse_id IS NULL AND h.name_key = e.horse_key AND coalesce(h.status, '') <> 'merged'
                 AND (SELECT count(*) FROM race_horses x WHERE x.name_key = e.horse_key
                      AND coalesce(x.status, '') <> 'merged') = 1""").rowcount
        print(f"stored {len(rows)} entries; re-linked {relinked} earlier unmatched entries")


if __name__ == "__main__":
    main()

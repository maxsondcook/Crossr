"""Record a stallion's death, pensioning, retirement or export (wins over his stud card).

Usage:
    python3 scripts/stallion_status.py set "Wootton Bassett" deceased --year 2008 --note "died 2026" --source user
    python3 scripts/stallion_status.py set "Some Horse" active          # undo: back to what the card says
    python3 scripts/stallion_status.py list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crossr_core import railway_db  # noqa: E402
from crossr_core import stallion_status as ss  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set")
    s.add_argument("name")
    s.add_argument("status", choices=sorted(ss.OFF_DUTY | {"active"}))
    s.add_argument("--year", type=int, help="foaling year, to tell namesakes apart")
    s.add_argument("--note")
    s.add_argument("--source", default="manual")
    sub.add_parser("list")
    args = ap.parse_args()
    with railway_db.connect() as conn:
        conn.execute(ss.SCHEMA)
        if args.cmd == "set":
            key = ss.name_key(args.name)
            if args.status == "active":
                conn.execute(f"DELETE FROM {ss.TABLE} WHERE name_key = %s", (key,))
            else:
                conn.execute(
                    f"""INSERT INTO {ss.TABLE} (name_key, foal_year, status, note, source) VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (name_key) DO UPDATE SET foal_year = EXCLUDED.foal_year, status = EXCLUDED.status,
                            note = EXCLUDED.note, source = EXCLUDED.source, updated_at = now()""",
                    (key, args.year, args.status, args.note, args.source))
            n = conn.execute(f"SELECT count(*) FROM {ss.TABLE}").fetchone()[0]
            railway_db._bump(conn, ss.TABLE, int(n))
            print(f"{key}: {args.status}")
        for row in conn.execute(f"SELECT name_key, foal_year, status, note, source, updated_at::date FROM {ss.TABLE} ORDER BY 1"):
            print(" ", row)


if __name__ == "__main__":
    main()

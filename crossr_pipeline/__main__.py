"""Crossr data pipeline. Needs DATABASE_URL (see scripts/pipeline/railway_env.sh).

    python -m crossr_pipeline scrape [--limit N] [--once] [--delay 3]
    python -m crossr_pipeline scrape --refresh-only [--refresh-cap N]
    python -m crossr_pipeline sales-import [--dry-run] [--force FILE ...]
    python -m crossr_pipeline racing-post [--limit N] [--delay 3]
    python -m crossr_pipeline status
    python -m crossr_pipeline install-launchd [--db railway|crossr_dev]

See docs/PIPELINE.md.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _conn():
    from equibase_scraper import pgdb

    if not pgdb.enabled():
        raise SystemExit(
            "DATABASE_URL is not set. Run through scripts/pipeline/railway_env.sh "
            "(railway or crossr_dev)."
        )
    return pgdb.connect()


def _db_name() -> str:
    return os.environ.get("DATABASE_URL", "").rsplit("/", 1)[-1].split("?")[0]


def cmd_scrape(args) -> int:
    from crossr_pipeline.scrape import scrape

    print(f"Database: {_db_name()}", flush=True)
    return scrape(
        delay=args.delay,
        limit=args.limit,
        refresh_cap=args.refresh_cap,
        once=args.once,
        skip_refresh=args.skip_refresh,
        refresh_only=args.refresh_only,
        role=args.role,
        catalogs_only=args.catalogs_only,
    )


def cmd_sales_import(args) -> int:
    from crossr_pipeline.sales_import import sales_import

    from crossr_pipeline.breeding_import import breeding_import
    from crossr_pipeline.sales_backfill import sales_backfill

    conn = _conn()
    try:
        force = set(args.force or [])
        if args.force_all:
            from crossr_pipeline.sales_import import SALES_DIR
            force = {path.name for path in SALES_DIR.glob("*.csv")}
        result = sales_import(conn, force=force, dry_run=args.dry_run)
        print(result)
        print(breeding_import(conn, dry_run=args.dry_run))
        if result["changed"] and not args.dry_run:
            print("Backfilling blank sales fields...", flush=True)
            sales_backfill(conn)
    finally:
        conn.close()
    return 1 if result["failed"] else 0


def cmd_sales_backfill(args) -> int:
    from crossr_pipeline.sales_backfill import counts, sales_backfill

    conn = _conn()
    try:
        before = counts(conn)
        sales_backfill(conn)
        after = counts(conn)
    finally:
        conn.close()
    _print_counts(before, after)
    return 0


def cmd_breeding_import(args) -> int:
    from crossr_pipeline.breeding_import import breeding_import

    conn = _conn()
    try:
        print(breeding_import(conn, dry_run=args.dry_run))
    finally:
        conn.close()
    return 0


def _print_counts(before: dict, after: dict) -> None:
    fields = ("damsire", "color", "foaled_location", "birth_year_blank", "mare_bad_year")
    print(f"{'year':<6}{'lots':>7}  " + "  ".join(f"{f:>22}" for f in fields))
    for year in sorted(after):
        b, a = before.get(year, {}), after[year]
        cells = [f"{b.get(f, 0):>9} -> {a[f]:<9}" for f in fields]
        print(f"{year:<6}{a['lots']:>7}  " + "  ".join(f"{c:>22}" for c in cells))


def cmd_racing_post(args) -> int:
    from crossr_pipeline.racing_post import run_racing_post

    print(f"Database: {_db_name()}", flush=True)
    while True:
        conn = _conn()
        try:
            done = run_racing_post(conn, delay=args.delay, limit=args.limit, gaps=args.gaps)
        finally:
            conn.close()
        if not args.loop or args.gaps:
            return 0
        if done == 0:
            print("racing-post: nothing due. Sleeping 6 h.", flush=True)
            time.sleep(6 * 3600)


def cmd_catalog_report(args) -> int:
    from crossr_pipeline import catalog_priority as cp

    conn = _conn()
    try:
        cp.ensure(conn)
        result = cp.report(conn, args.catalog)
        job = conn.execute("SELECT * FROM crossr_catalog_jobs WHERE catalog_id = %s", (args.catalog,)).fetchone()
    finally:
        conn.close()
    for key, value in sorted(result["counts"].items()):
        print(f"  {key:<24} {value}")
    if job:
        print(f"  job: {job['status']}  {job['detail'] or ''}")
    print(f"  incomplete hips: {len(result['incomplete'])}")
    for hip, label, needs in result["incomplete"][: args.show]:
        print(f"    {hip:>5}  {label[:45]:<45}  needs {needs}")
    return 0


def cmd_catalog_enrich(args) -> int:
    from pathlib import Path

    from crossr_pipeline import keeneland

    export = Path(args.export) if args.export else REPO / "logs" / "pipeline" / f"{args.catalog}.keeneland.csv"
    if args.url:
        keeneland.export_catalog(args.url, export, REPO / "crossr_pipeline" / "chrome_profile_keeneland")
    csv_path = REPO / "Upcoming Sales" / f"{args.catalog}.csv"
    conn = _conn()
    try:
        filled = keeneland.enrich_catalog(conn, args.catalog, export, csv_path if csv_path.exists() else None)
    finally:
        conn.close()
    print(filled)
    return 0


def cmd_fees_redate(args) -> int:
    from crossr_pipeline import fee_redate as fr

    conn = _conn()
    try:
        ranking_rows, rows, rp = fr.load(conn)
        new_rows, stats, conflicts = fr.rebuild(ranking_rows, rows, rp, early=args.early)
        print(f"Database: {_db_name()}  early lists: {args.early}  stud_fees {len(rows)} -> {len(new_rows)} rows; "
              f"gap years {fr.gaps(rows)} -> {fr.gaps(new_rows)}")
        for key, value in sorted(stats.items()):
            print(f"  {key:<42} {value}")
        print("  conflict examples (stallion, season, CSV kept, Racing Post):")
        for c in sorted(conflicts, key=lambda c: -c[1])[:8]:
            print(f"    {c}")
        for key in fr.EXAMPLES:
            before, after = fr.fee_table(rows, key), fr.fee_table(new_rows, key)
            print(f"\n{key}")
            for i in range(max(len(before), len(after))):
                b = before[i] if i < len(before) else ""
                a = after[i] if i < len(after) else ""
                print(f"  {b:<52} | {a}")
        if args.apply:
            backup = fr.apply(conn, new_rows)
            print(f"\nApplied. Previous table saved as {backup}.")
    finally:
        conn.close()
    return 0


def _age(ts) -> str:
    if ts is None:
        return "-"
    seconds = (datetime.now(timezone.utc) - ts).total_seconds()
    if seconds < 120:
        return f"{int(seconds)}s ago"
    if seconds < 7200:
        return f"{int(seconds // 60)}m ago"
    if seconds < 172800:
        return f"{seconds / 3600:.1f}h ago"
    return f"{seconds / 86400:.1f}d ago"


def cmd_status(args) -> int:
    from crossr_pipeline import state

    conn = _conn()
    try:
        state.ensure(conn)
        print(f"Database: {_db_name()}\n")
        print("Recent runs")
        for run in state.recent_runs(conn, args.limit):
            status = run["status"]
            if status == "running" and run["heartbeat_at"] and (
                datetime.now(timezone.utc) - run["heartbeat_at"]
            ).total_seconds() > 3600:
                status = "running? (no heartbeat for 1h+, probably crashed)"
            counts = ", ".join(f"{k}={v}" for k, v in sorted((run["counts"] or {}).items()))
            print(
                f"  #{run['id']:<5} {run['job']:<16} {status:<10} started {_age(run['started_at'])}, "
                f"heartbeat {_age(run['heartbeat_at'])}  {counts}"
            )
            if run["detail"]:
                print(f"         {run['detail']}")
        print("\nQueue items")
        for row in state.queue_summary(conn):
            print(f"  {row['job']:<16} {row['status']:<14} {row['n']}")
        print("\nrace_horses by status")
        for row in conn.execute("SELECT status, COUNT(*) AS n FROM race_horses GROUP BY 1 ORDER BY 2 DESC"):
            print(f"  {row['status'] or '-':<14} {row['n']}")
        print("\nTable versions (API reloads when these move)")
        for row in conn.execute("SELECT table_name, row_count, updated_at FROM crossr_table_versions ORDER BY 1"):
            print(f"  {row['table_name']:<18} {row['row_count'] or 0:>9}  {_age(row['updated_at'])}")
    finally:
        conn.close()
    return 0


def cmd_install_launchd(args) -> int:
    from crossr_pipeline import launchd

    paths = launchd.write_plists(db=args.db, python=args.python or sys.executable)
    for path in paths:
        print(f"wrote {path}")
    print("\nNothing is loaded yet. To start:")
    for path in paths:
        print(f"  launchctl bootstrap gui/$(id -u) {path}")
    print("To stop:")
    for path in paths:
        print(f"  launchctl bootout gui/$(id -u) {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m crossr_pipeline", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scrape", help="Equibase loop: weekly race refresh + sale-parent pedigrees")
    p.add_argument("--delay", type=float, default=3.0, help="Seconds between page loads (plus jitter)")
    p.add_argument("--limit", type=int, help="Stop after this many queue items (testing)")
    p.add_argument("--once", action="store_true", help="One pass over the queue, then exit")
    p.add_argument("--refresh-cap", type=int, help="At most this many horses in a race refresh")
    p.add_argument("--skip-refresh", action="store_true", help="Do not run the weekly race refresh")
    p.add_argument("--refresh-only", action="store_true", help="Run only the race refresh, then exit")
    p.add_argument("--role", choices=["sire", "dam"], help="Only sale sires or only sale dams")
    p.add_argument("--catalogs-only", action="store_true",
                   help="Only run queued upcoming catalogs (with --limit: that many hips each), then exit")
    p.set_defaults(func=cmd_scrape)

    p = sub.add_parser("sales-import", help="Load new/changed sales_data/*.csv into sales_lots")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", nargs="*", metavar="FILE", help="Reload these file names even if unchanged")
    p.add_argument("--force-all", action="store_true", help="Reload every sales file (after a parser change)")
    p.set_defaults(func=cmd_sales_import)

    p = sub.add_parser("sales-backfill", help="Fill blank damsire/color/foaled/birth year in sales_lots from our other data")
    p.set_defaults(func=cmd_sales_backfill)

    p = sub.add_parser("breeding-import", help="Load live_foal_statistics/*.csv years into breeding_seasons")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_breeding_import)

    p = sub.add_parser("racing-post", help="Racing Post fee history for every sire (adds missing stud_fees years)")
    p.add_argument("--delay", type=float, default=3.0, help="Seconds between page loads (plus jitter)")
    p.add_argument("--limit", type=int, help="Stop after this many sires (testing)")
    p.add_argument("--loop", action="store_true", help="Keep going: rerun when done, sleep 6 h when nothing is due")
    p.add_argument("--gaps", action="store_true",
                   help="Re-scrape active stallions with missing fee years (Not This Time first), then exit")
    p.set_defaults(func=cmd_racing_post)

    p = sub.add_parser("catalog-report", help="Completeness of an upcoming catalog's hips")
    p.add_argument("catalog", help="upcoming_catalogs id, e.g. 'Keeneland November Breeding Stock Sale (2026)'")
    p.add_argument("--show", type=int, default=25, help="How many incomplete hips to list")
    p.set_defaults(func=cmd_catalog_report)

    p = sub.add_parser("catalog-enrich", help="Fill SESSION/BOOK/COLOR/SIRE OF DAM/YEAR OF BIRTH from Keeneland's catalog")
    p.add_argument("catalog", help="upcoming_catalogs id")
    p.add_argument("--url", help="Keeneland catalog-table URL to export from")
    p.add_argument("--export", help="An already exported Keeneland CSV")
    p.set_defaults(func=cmd_catalog_enrich)

    p = sub.add_parser("fees-redate", help="Re-date stud_fees by breeding season (dry run unless --apply)")
    p.add_argument("--apply", action="store_true", help="Back up stud_fees, then replace it")
    p.add_argument("--early", choices=["header", "list-year"], default="header",
                   help="2001-2007 lists: season from the file header (default) or the list year")
    p.set_defaults(func=cmd_fees_redate)

    p = sub.add_parser("status", help="Recent runs, queue state, table counts")
    p.add_argument("--limit", type=int, default=15)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("install-launchd", help="Write the launchd agents (does not load them)")
    p.add_argument("--db", default="railway", help="railway (production) or crossr_dev")
    p.add_argument("--python", help="Python to run (default: this one)")
    p.set_defaults(func=cmd_install_launchd)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

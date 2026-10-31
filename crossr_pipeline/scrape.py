"""The Equibase scrape, in short batches: one Chrome window per batch, closed
at the end, and no per-horse traffic to Railway.

Each batch (about BATCH_MINUTES):
  0. stage.prepare: push anything left from the last batch, pull what someone
     else changed (normally nothing), reserve race_horses ids.
  1. Upcoming catalogs first (catalog_priority): their results are pushed at
     least every 30 min, so hips on the site turn complete as data lands.
  2. races-refresh, when the last finished one is over a week old: re-open
     the profile of every ok horse with a start in the last 60 days.
  3. pedigrees-sales: the sire and dam of every sale lot, to a full 5-gen
     tree (see sales_parents).
Everything is read from and written to the local stage (state/stage.sqlite);
the daily ``push`` job sends race records and pedigrees to Postgres.

Exit status: 0 when there is nothing left to do (launchd starts the next
batch at its interval), EXIT_MORE when work remains (launchd starts the next
batch a minute later, with a fresh Chrome).

A block page pauses the batch and sends a Mac notification every hour until
someone clears the check in the open Chrome window. Nothing here tries to get
past the check on its own.
"""

from __future__ import annotations

import fcntl
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crossr_pipeline import notify, sales_parents, stage, state

REPO = Path(__file__).resolve().parents[1]
LOG_DIR = REPO / "logs" / "pipeline"
LOCK_PATH = LOG_DIR / "chrome.lock"  # shared with racing_post: one browser at a time

REFRESH_JOB = "races-refresh"
REFRESH_EVERY_DAYS = 7
REFRESH_WINDOW_DAYS = 60
BATCH_MINUTES = 45
HEARTBEAT_EVERY = 25
MAX_ERRORS_IN_A_ROW = 8
EXIT_MORE = 75  # EX_TEMPFAIL: more work waiting

# What the scraper does not download: pictures, video, fonts, and ad /
# tracking hosts. Pages and their own scripts (block checks included) load as
# before; while a block page is up everything loads, so the check can be done.
SKIP_TYPES = {"image", "media", "font"}
SKIP_HOSTS = (
    "doubleclick.net", "googlesyndication.com", "google-analytics.com", "googletagmanager.com",
    "googletagservices.com", "adservice.google.com", "facebook.net", "facebook.com", "adnxs.com",
    "amazon-adsystem.com", "scorecardresearch.com", "taboola.com", "outbrain.com", "criteo.com",
    "criteo.net", "quantserve.com", "moatads.com", "rubiconproject.com", "pubmatic.com", "casalemedia.com",
    "openx.net", "hotjar.com", "newrelic.com", "nr-data.net", "chartbeat.com", "twitter.com", "linkedin.com",
)
CHROME_ARGS = ["--renderer-process-limit=2", "--disable-background-networking", "--disable-component-update"]


def _run_module():
    from equibase_scraper import run as eb

    eb.db = stage  # find_horses, save_profile, ... now read and write the local stage
    return eb


def take_lock(wait: bool = False):
    """The Chrome lock, or None when another Chrome job holds it (wait=False)."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handle = LOCK_PATH.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
    except BlockingIOError:
        handle.close()
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


class Lightener:
    """Route handler that drops SKIP_TYPES and SKIP_HOSTS while ``on``."""

    def __init__(self):
        self.on = True
        self.skipped = 0

    def __call__(self, route) -> None:
        request = route.request
        if self.on and (request.resource_type in SKIP_TYPES or any(
                h in (request.url.split("/")[2] if "//" in request.url else "") for h in SKIP_HOSTS)):
            self.skipped += 1
            route.abort()
        else:
            route.continue_()


def wait_out_block(eb, page, horse, run: state.Run, light: Lightener | None = None) -> None:
    """Block until the page is clear. Re-notify every hour; never give up."""
    require_seen = False
    if light is not None:
        light.on = False  # the check may need its pictures
    try:
        while True:
            run.heartbeat("blocked: clear the check in the Chrome window")
            notify.send("Equibase block page", "Clear the check in the Crossr Chrome window to continue.")
            if eb.wait_until_clear(page, horse=horse, require_seen_block=require_seen, timeout_s=3600):
                run.heartbeat("running")
                return
            require_seen = True
            horse = None
    finally:
        if light is not None:
            light.on = True


_LIGHT: Lightener | None = None


def _with_block_retry(eb, page, run, horse, action):
    while True:
        try:
            return action()
        except eb.Blocked:
            run.bump("blocks")
            wait_out_block(eb, page, horse, run, _LIGHT)


# ---------------------------------------------------------------------------
# races-refresh
# ---------------------------------------------------------------------------

def refresh_due(conn) -> bool:
    last = state.last_run(conn, REFRESH_JOB, "ok")
    if last is None:
        return True
    return datetime.now(timezone.utc) - last["started_at"] >= timedelta(days=REFRESH_EVERY_DAYS)


def refresh_candidates(conn, cap: int | None, local=None) -> list[dict]:
    """Ok horses with a recent start (Postgres, which has the starts), minus
    those the stage re-fetched since (not pushed yet)."""
    since = (datetime.now(timezone.utc) - timedelta(days=REFRESH_WINDOW_DAYS)).date().isoformat()
    fetched_before = (datetime.now(timezone.utc) - timedelta(days=REFRESH_EVERY_DAYS - 1)).isoformat()
    sql = """
        SELECT h.*, s.last_start FROM race_horses h
        JOIN (
            SELECT horse_id, MAX(race_date) AS last_start FROM race_starts
            WHERE race_date >= %s GROUP BY horse_id
        ) s ON s.horse_id = h.id
        WHERE h.status = 'ok' AND COALESCE(h.profile_url, '') <> ''
          AND COALESCE(h.fetched_at, '') < %s
        ORDER BY s.last_start DESC
    """
    rows = [dict(r) for r in conn.execute(sql, (since, fetched_before)).fetchall()]
    if local is not None and rows:
        fetched = stage.fetched_at_by_id(local, [r["id"] for r in rows])
        rows = [r for r in rows if fetched.get(str(r["id"]), "") < fetched_before]
    return rows[:cap] if cap else rows


def refresh_one(eb, page, conn, horse: dict, delay: float) -> str:
    """Re-open a known profile (one page load) and replace its record."""
    eb.polite_wait(page, delay)
    html, err = eb.goto_profile(page, horse["profile_url"])
    if eb.is_blocked(html or ""):
        raise eb.Blocked()
    if err or not html:
        return "error"
    resolved = eb.resolve_html(html, horse.get("foal_year") or "")
    if resolved["kind"] == "blocked":
        raise eb.Blocked()
    if resolved["kind"] != "profile":
        return "error"
    eb._store_resolved(conn, horse["id"], resolved)
    return "ok"


def run_refresh(eb, page, pg, local, delay: float, cap: int | None, deadline: float) -> bool:
    """Returns True when every candidate is done (the refresh is finished)."""
    horses = refresh_candidates(pg, cap, local)
    run = state.Run(pg, REFRESH_JOB)
    print(f"races-refresh: {len(horses)} horse(s) with a start in the last {REFRESH_WINDOW_DAYS} days", flush=True)
    done = 0
    try:
        for index, horse in enumerate(horses, start=1):
            if time.monotonic() >= deadline:
                break
            try:
                result = _with_block_retry(eb, page, run, horse, lambda: refresh_one(eb, page, local, horse, delay))
            except Exception as exc:  # one bad page should not stop the refresh
                print(f"refresh error {horse['pedigree_key']}: {exc}", flush=True)
                result = "error"
            done = index
            run.bump(result)
            print(f"[refresh {index}/{len(horses)}] {horse['pedigree_key']}: {result}", flush=True)
            if index % HEARTBEAT_EVERY == 0:
                run.heartbeat("running")
    except BaseException as exc:
        run.finish("partial", f"stopped: {exc.__class__.__name__}")
        raise
    finished = done >= len(horses)
    run.finish("ok" if finished else "partial", f"{done} of {len(horses)} horses")
    return finished


# ---------------------------------------------------------------------------
# pedigrees-sales
# ---------------------------------------------------------------------------

def _row_for_item(eb, conn, item: dict) -> tuple[dict | None, str]:
    db = eb.db
    rows = db.find_horses(conn, item["name_key"], item["name_key"], None)
    row, why = sales_parents.pick_row(rows, item)
    if row is not None or why == "ambiguous rows":
        return row, why
    key = sales_parents.new_row_key(item, lambda k: db.key_taken(conn, k))
    db.insert_batch_horse(
        conn,
        {
            "pedigree_key": key,
            "name_key": item["name_key"],
            "display_name": item["name"],
            "sire": item["sire"] if item["role"] == "dam" else "",
            "sex": "",
            "queue_batch": sales_parents.QUEUE_BATCH,
        },
    )
    hits = [hit for hit in db.find_horses(conn, key, item["name_key"], None) if hit["pedigree_key"] == key]
    return (hits[0] if hits else None), ("" if hits else "insert failed")


def process_item(eb, page, conn, book, item: dict, delay: float) -> tuple[str, str]:
    """Fetch one sale parent if needed, then fill its tree. Returns (status, detail)."""
    row, why = _row_for_item(eb, conn, item)
    if row is None:
        return ("ambiguous" if why == "ambiguous rows" else "error"), why
    horse = dict(eb.follow_merged(conn, row))
    if horse["status"] in sales_parents.DONE:
        return horse["status"], f"race_horses {horse['id']}"
    if horse["status"] != "ok":
        horse["role"] = item["role"]
        horse["yob_range"] = item["yob_range"]
        if item["role"] == "dam" and not horse.get("sire") and item["sire"]:
            horse["sire"] = item["sire"]
        eb.fetch_horse(page, conn, horse, delay)
        horse = dict(eb.follow_merged(conn, eb.db.get_by_id(conn, horse["id"])))
        if horse["status"] != "ok":
            return horse["status"], horse.get("detail") or ""
    eb.fill_horse_pedigree(page, conn, horse, book, delay)
    if eb._subject_is_complete(book, horse):
        return "complete", f"race_horses {horse['id']}"
    return "incomplete", f"race_horses {horse['id']}"


def sale_parents(pg, local) -> list[dict]:
    """sales_parents.load_parents, re-read only when sales_lots changes."""
    from crossr_core import pg_push as push

    version = push.table_versions(pg, ("sales_lots",)).get("sales_lots", "")
    return stage.cached(local, "sale_parents", version, lambda: sales_parents.load_parents(pg))


def run_pedigrees(eb, page, pg, local, book, delay: float, limit: int | None, deadline: float,
                  role: str | None = None, hook=None) -> int:
    """Work the queue until it is empty or the batch is out of time. Returns items left."""
    states = stage.queue_states(local, sales_parents.JOB)
    todo, skipped = sales_parents.build_queue(sale_parents(pg, local), book.index, states, time.time(), limit, role)
    run = state.Run(pg, sales_parents.JOB)
    for reason, n in skipped.items():
        run.counts[f"skipped: {reason}"] = n
    print(f"pedigrees-sales: {len(todo)} to do; skipped {dict(skipped)}", flush=True)
    run.heartbeat("running")
    errors_in_a_row = 0
    done = 0
    try:
        for index, item in enumerate(todo, start=1):
            if time.monotonic() >= deadline:
                break
            label = f"{item['role']} {item['name']}" + (f" (by {item['sire']})" if item["sire"] else "")
            print(f"[{index}/{len(todo)}] {label}", flush=True)
            saved_before = book.saved
            try:
                result, detail = _with_block_retry(
                    eb, page, run, {"display_name": item["name"], "pedigree_key": item["name_key"]},
                    lambda: process_item(eb, page, local, book, item, delay),
                )
                errors_in_a_row = 0 if result != "error" else errors_in_a_row + 1
            except Exception as exc:
                result, detail = "error", f"{exc.__class__.__name__}: {exc}"
                errors_in_a_row += 1
                print(f"  error: {detail}", flush=True)
            stage.mark_item(local, sales_parents.JOB, item["key"], result, detail)
            done = index
            run.bump(result)
            run.bump("trees saved", book.saved - saved_before)
            print(f"  -> {result} {detail}", flush=True)
            if errors_in_a_row >= MAX_ERRORS_IN_A_ROW:
                raise RuntimeError(f"{errors_in_a_row} errors in a row; stopping (Chrome closed?)")
            if index % HEARTBEAT_EVERY == 0:
                run.heartbeat("running")
            if hook is not None:
                hook()  # a newly published catalog runs here, ahead of this queue
    except BaseException as exc:
        run.finish("failed" if isinstance(exc, RuntimeError) else "partial", f"stopped: {exc}")
        raise
    left = len(todo) - done
    run.finish("ok" if not left else "partial", f"{done} of {len(todo)} items")
    return left


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def scrape(delay: float = 3.0, limit: int | None = None, refresh_cap: int | None = None,
           skip_refresh: bool = False, refresh_only: bool = False, role: str | None = None,
           catalogs_only: bool = False, minutes: float = BATCH_MINUTES, light: bool = True) -> int:
    """One batch. Returns 0 (nothing left) or EXIT_MORE (run again soon)."""
    global _LIGHT
    from playwright.sync_api import sync_playwright

    from equibase_scraper import pgdb

    eb = _run_module()
    lock = take_lock()
    if lock is None:
        print("Another Chrome job (scrape or racing-post) is running; trying again next interval.", flush=True)
        return 0
    pg = pgdb.connect()
    local = stage.connect()
    more = False
    try:
        state.ensure(pg)
        stage.prepare(local, pg, log=lambda m: print(m, flush=True))
        deadline = time.monotonic() + minutes * 60
        book = None if refresh_only else eb._PedigreeBook(local)
        with sync_playwright() as playwright:
            context, page = eb._launch_context(playwright, extra_args=CHROME_ARGS)
            _LIGHT = Lightener() if light else None
            if _LIGHT is not None:
                context.route("**/*", _LIGHT)
            try:
                if not eb.warmup(page):
                    boot = state.Run(pg, "warmup")
                    wait_out_block(eb, page, None, boot, _LIGHT)
                    boot.finish("ok")
                hook = None
                if book is not None:
                    from crossr_pipeline.catalog_priority import Hook

                    hook = Hook(eb, page, pg, book, delay, limit=limit if catalogs_only else None, local=local,
                                deadline=deadline)
                    hook(force=True)
                    more = more or hook.left > 0
                if not catalogs_only:
                    if not skip_refresh and (refresh_only or refresh_due(pg)) and time.monotonic() < deadline:
                        more = more or not run_refresh(eb, page, pg, local, delay, refresh_cap, deadline)
                    if not refresh_only and time.monotonic() < deadline:
                        left = run_pedigrees(eb, page, pg, local, book, delay, limit, deadline, role, hook)
                        more = more or (left > 0 and not limit)
                        more = more or (hook is not None and hook.left > 0)
            finally:
                if _LIGHT is not None:
                    print(f"Skipped {_LIGHT.skipped} picture/font/ad requests.", flush=True)
                context.close()
    except KeyboardInterrupt:
        print("Stopped.", flush=True)
        return 130
    except Exception as exc:
        notify.send("Crossr scrape stopped", str(exc)[:200])
        raise
    finally:
        print(f"Staged, waiting for the daily push: {stage.pending(local)}", flush=True)
        local.close()
        pg.close()
        lock.close()
    return EXIT_MORE if more else 0

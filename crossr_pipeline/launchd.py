"""launchd agents for the pipeline (written, never loaded, by install-launchd).

Collection agents are intentionally not written. See crossr_pipeline/collection.py
(COLLECTION_ENABLED = False). This file cannot unload a job already running
from ~/Crossr-pipeline. Those labels:

    com.crossr.pipeline.scrape        Equibase hourly batch (off)
    com.crossr.pipeline.racing-post   Racing Post fee pages (off)
    com.crossr.pipeline.mares-bred    Jockey Club Report of Mares Bred (off)
    com.crossr.pipeline.entries       NYRA published entries (off)
    com.crossr.pipeline.stallion-news Thoroughbred Daily News crawl (off)

Still written, because they do not fetch from those sites:

    com.crossr.pipeline.push          daily at 03:00: staged rows already on this Mac -> Postgres
    com.crossr.pipeline.sales-import  daily at 07:00: local sales_data/*.csv (run at wake if the Mac slept)
    com.crossr.pipeline.precompute    nightly 02:30: sales-model hip pages from data already stored
    com.crossr.pipeline.weekly        Monday 08:00 (run at wake if the Mac slept): weekly lists and emails
    com.crossr.pipeline.audit         daily 05:30: read-only data audit

The Chrome lock (logs/pipeline/chrome.lock) is unused while collection is off.

All of them run through scripts/pipeline/railway_env.sh, so DATABASE_URL is built
from the Railway CLI at start and no password is written to disk. The scrapers
run under ``caffeinate -i`` so the Mac does not idle-sleep mid-run.
"""

from __future__ import annotations

import plistlib
from pathlib import Path

from crossr_pipeline.collection import LAUNCHD_COLLECTION_LABELS

REPO = Path(__file__).resolve().parents[1]
AGENTS = Path.home() / "Library" / "LaunchAgents"
LOG_DIR = REPO / "logs" / "pipeline"
SCRAPE = "com.crossr.pipeline.scrape"
SALES = "com.crossr.pipeline.sales-import"
RACING_POST = "com.crossr.pipeline.racing-post"
PUSH = "com.crossr.pipeline.push"
MARES_BRED = "com.crossr.pipeline.mares-bred"
PRECOMPUTE = "com.crossr.pipeline.precompute"
WEEKLY = "com.crossr.pipeline.weekly"
AUDIT = "com.crossr.pipeline.audit"
STALLION_NEWS = "com.crossr.pipeline.stallion-news"
ENTRIES = "com.crossr.pipeline.entries"


def plists(db: str, python: str) -> dict[str, dict]:
    env = str(REPO / "scripts" / "pipeline" / "railway_env.sh")
    common = {
        "WorkingDirectory": str(REPO),
        "EnvironmentVariables": {
            "PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin",
            "PYTHONUNBUFFERED": "1",
        },
        "ProcessType": "Interactive",
    }
    # Collection jobs stay in this dict so the definitions are visible, then
    # they are dropped. install-launchd does not write them.
    defined = {
        SCRAPE: {
            "Label": SCRAPE,
            "ProgramArguments": [env, db, "/usr/bin/caffeinate", "-i", python, "-m", "crossr_pipeline", "scrape"],
            "RunAtLoad": True,
            "StartInterval": 3600,
            "KeepAlive": {"SuccessfulExit": False},
            "ThrottleInterval": 60,
            "StandardOutPath": str(LOG_DIR / "scrape.log"),
            "StandardErrorPath": str(LOG_DIR / "scrape.log"),
            **common,
        },
        PUSH: {
            "Label": PUSH,
            "ProgramArguments": [env, db, python, "-m", "crossr_pipeline", "push"],
            "StartCalendarInterval": {"Hour": 3, "Minute": 0},
            "StandardOutPath": str(LOG_DIR / "push.log"),
            "StandardErrorPath": str(LOG_DIR / "push.log"),
            **common,
        },
        SALES: {
            "Label": SALES,
            "ProgramArguments": [env, db, python, "-m", "crossr_pipeline", "sales-import"],
            "StartCalendarInterval": {"Hour": 7, "Minute": 0},
            "StandardOutPath": str(LOG_DIR / "sales-import.log"),
            "StandardErrorPath": str(LOG_DIR / "sales-import.log"),
            **common,
        },
        RACING_POST: {
            "Label": RACING_POST,
            "ProgramArguments": [env, db, "/usr/bin/caffeinate", "-i", python, "-m", "crossr_pipeline", "racing-post"],
            "StartCalendarInterval": {"Weekday": 0, "Hour": 4, "Minute": 0},
            "StandardOutPath": str(LOG_DIR / "racing-post.log"),
            "StandardErrorPath": str(LOG_DIR / "racing-post.log"),
            **common,
        },
        # Away from sales-import (07:00, also writes breeding_seasons) and the Chrome jobs.
        MARES_BRED: {
            "Label": MARES_BRED,
            "ProgramArguments": [env, db, python, str(REPO / "scripts" / "jockeyclub_mares_bred.py"), "--apply"],
            "StartCalendarInterval": {"Weekday": 6, "Hour": 5, "Minute": 0},
            "StandardOutPath": str(LOG_DIR / "mares-bred.log"),
            "StandardErrorPath": str(LOG_DIR / "mares-bred.log"),
            **common,
        },
        # Sales-model hip pages: every upcoming catalog, stale hips only.
        PRECOMPUTE: {
            "Label": PRECOMPUTE,
            "ProgramArguments": [env, db, python, str(REPO / "scripts" / "precompute_catalogs.py")],
            "StartCalendarInterval": {"Hour": 2, "Minute": 30},
            "StandardOutPath": str(LOG_DIR / "precompute.log"),
            "StandardErrorPath": str(LOG_DIR / "precompute.log"),
            **common,
        },
        # Safe to re-run: reports are upserted and emails already sent are skipped.
        WEEKLY: {
            "Label": WEEKLY,
            "ProgramArguments": [str(Path.home() / ".local" / "railway-cli" / "node_modules" / ".bin" / "railway"),
                                 "run", "-s", "api", "--", env, db, python, "-m", "crossr_core.weekly", "run"],
            "StartCalendarInterval": {"Weekday": 1, "Hour": 8, "Minute": 0},
            "StandardOutPath": str(LOG_DIR / "weekly.log"),
            "StandardErrorPath": str(LOG_DIR / "weekly.log"),
            **common,
        },
        # Before the Monday 08:00 weekly job, so Monday's list has the latest cards.
        ENTRIES: {
            "Label": ENTRIES,
            "ProgramArguments": [env, db, python, "-m", "crossr_pipeline", "entries", "--apply"],
            "StartCalendarInterval": {"Hour": 6, "Minute": 15},
            "StandardOutPath": str(LOG_DIR / "entries.log"),
            "StandardErrorPath": str(LOG_DIR / "entries.log"),
            **common,
        },
        AUDIT: {
            "Label": AUDIT,
            "ProgramArguments": [env, db, python, str(REPO / "scripts" / "data_audit.py")],
            "StartCalendarInterval": {"Hour": 5, "Minute": 30},
            "StandardOutPath": str(LOG_DIR / "audit.log"),
            "StandardErrorPath": str(LOG_DIR / "audit.log"),
            **common,
        },
        STALLION_NEWS: {
            "Label": STALLION_NEWS,
            "ProgramArguments": [env, db, python, str(REPO / "scripts" / "stallion_news_watch.py"), "--apply"],
            "StartCalendarInterval": {"Hour": 6, "Minute": 0},
            "StandardOutPath": str(LOG_DIR / "stallion-news.log"),
            "StandardErrorPath": str(LOG_DIR / "stallion-news.log"),
            **common,
        },
    }
    return {label: body for label, body in defined.items() if label not in LAUNCHD_COLLECTION_LABELS}


def write_plists(db: str, python: str) -> list[Path]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    AGENTS.mkdir(parents=True, exist_ok=True)
    out = []
    for label, body in plists(db, python).items():
        path = AGENTS / f"{label}.plist"
        with path.open("wb") as handle:
            plistlib.dump(body, handle)
        out.append(path)
    return out

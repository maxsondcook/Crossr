"""launchd agents for the pipeline (written, never loaded, by install-launchd).

    com.crossr.pipeline.scrape        one 45-min Equibase batch an hour; when work is
                                      waiting (exit 75) the next batch starts a minute later
    com.crossr.pipeline.push          daily at 03:00: staged race records and pedigrees -> Postgres
    com.crossr.pipeline.sales-import  daily at 07:00 (run at wake if the Mac slept)
    com.crossr.pipeline.racing-post   weekly, Sunday 04:00: sires due a fee lookup, one push at the end
    com.crossr.pipeline.mares-bred    weekly, Saturday 05:00: The Jockey Club's Report of Mares Bred
                                      -> breeding_seasons (one page; scripts/jockeyclub_mares_bred.py)
    com.crossr.pipeline.precompute    nightly 02:30: sales-model hip pages for upcoming catalogs

The two Chrome jobs (scrape, racing-post) share logs/pipeline/chrome.lock, so
only one browser is open at a time.

All of them run through scripts/pipeline/railway_env.sh, so DATABASE_URL is built
from the Railway CLI at start and no password is written to disk. The scrapers
run under ``caffeinate -i`` so the Mac does not idle-sleep mid-run.
"""

from __future__ import annotations

import plistlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
AGENTS = Path.home() / "Library" / "LaunchAgents"
LOG_DIR = REPO / "logs" / "pipeline"
SCRAPE = "com.crossr.pipeline.scrape"
SALES = "com.crossr.pipeline.sales-import"
RACING_POST = "com.crossr.pipeline.racing-post"
PUSH = "com.crossr.pipeline.push"
MARES_BRED = "com.crossr.pipeline.mares-bred"
PRECOMPUTE = "com.crossr.pipeline.precompute"


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
    return {
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
    }


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

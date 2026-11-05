"""Nightly bug hunt: unit tests, data audit, and live checks of the site's main features.

    python -m tests.nightly                 # everything (needs DATABASE_URL for the audit)
    python -m tests.nightly --skip-audit    # unit tests + live checks only
    python -m tests.nightly --quick         # fewer live samples

Writes an agent-ready bug list to ``bugs/latest.md`` (and ``bugs/inbox/<date>.md`` / ``.json``):
each bug has an id, area, what failed, how to reproduce it, expected vs actual, and the
files most likely involved. A scheduled AI agent reads it each morning and fixes what it
can on a branch; any agent (Claude Code, Cursor) can start from it. Exit code 1 when
anything failed.
"""

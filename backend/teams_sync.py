"""Teams list sync from OpenDota /teams into d2ba.sqlite (used by team search).

A sync is about 20 paged requests, so it runs from the UI button (POST /api/teams/sync) and at startup in a
background thread when the last successful sync is 30+ days old (or never happened). One sync runs at a time.
"""

import sqlite3
import threading
import time
from typing import Optional

from flask import Flask
from werkzeug.serving import is_running_from_reloader

from backend.logging_config import setup_logging
from backend.pro_players import fetch_teams_from_api, get_d2ba_db, store_teams

logger = setup_logging(__name__)

TEAMS_SYNC_NAME = "teams"  # sync_state.name of the teams list
TEAMS_MAX_AGE_SECONDS = 30 * 24 * 60 * 60

_sync_lock = threading.Lock()


class TeamsSyncRunningError(Exception):
    """A teams sync is already running (from the button or the startup check)."""


def get_teams_synced_at() -> Optional[int]:
    """Time of the last successful teams sync.

    Returns:
        Unix seconds, or None when the teams list was never synced
    """
    row = get_d2ba_db().execute("SELECT synced_at FROM sync_state WHERE name = ?", (TEAMS_SYNC_NAME,)).fetchone()
    return row["synced_at"] if row else None


def is_teams_sync_running() -> bool:
    """Whether a teams sync is running in this process."""
    return _sync_lock.locked()


def is_teams_sync_due(now: Optional[float] = None) -> bool:
    """Whether the teams list was never synced or the last sync is 30+ days old.

    Args:
        now: Current unix time (defaults to time.time())

    Returns:
        True when a sync is needed
    """
    synced_at = get_teams_synced_at()
    current = time.time() if now is None else now
    return synced_at is None or current - synced_at >= TEAMS_MAX_AGE_SECONDS


def run_teams_sync() -> int:
    """Fetch all teams from OpenDota, store them and record the sync time (only when teams were stored).

    Returns:
        Number of teams stored

    Raises:
        TeamsSyncRunningError: If another sync is running
        ConnectionError: If OpenDota could not be reached
        ValueError: If the OpenDota answer is invalid
    """
    if not _sync_lock.acquire(blocking=False):
        raise TeamsSyncRunningError("Teams sync is already running")
    try:
        count = store_teams(fetch_teams_from_api())
        if count:
            db = get_d2ba_db()
            db.execute(
                """
                INSERT INTO sync_state (name, synced_at) VALUES (?, ?)
                ON CONFLICT(name) DO UPDATE SET synced_at = excluded.synced_at
                """,
                (TEAMS_SYNC_NAME, int(time.time())),
            )
            db.commit()
        return count
    finally:
        _sync_lock.release()


def _sync_in_background(app: Flask) -> None:
    """Run a teams sync in its own app context; errors are logged."""
    try:
        with app.app_context():
            count = run_teams_sync()
            logger.info(f"Startup teams sync stored {count} teams")
    except TeamsSyncRunningError:
        logger.info("Startup teams sync skipped, a sync is already running")
    except Exception as e:
        logger.error(f"Error syncing teams on startup: {e}")


def sync_teams_on_startup(app: Flask) -> Optional[threading.Thread]:
    """Start a background teams sync when it is due, without blocking the startup.

    With the debug reloader, only the serving child process syncs (the watching parent also creates the app).

    Args:
        app: Flask app

    Returns:
        The started thread, or None when no sync is needed
    """
    if app.debug and not is_running_from_reloader():
        return None
    try:
        with app.app_context():
            if not is_teams_sync_due():
                return None
    except sqlite3.Error as e:
        logger.error(f"Error checking teams sync time on startup: {e}")
        return None
    logger.info("Teams list is older than 30 days or was never synced, syncing in the background")
    thread = threading.Thread(target=_sync_in_background, args=(app,), name="teams-sync", daemon=True)
    thread.start()
    return thread

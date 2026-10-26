"""Teams list sync from OpenDota into d2ba.sqlite (used by team search and the Matches tab).

The list is updated on its own when it is obsolete (last successful sync 24+ hours old, or never): at startup and
on team search / matches requests, in a background thread. One sync runs at a time.

- Full sync (teams table empty, or POST /api/teams/sync?full=1): every `/teams` page, about 22 requests.
- Incremental sync (otherwise): two explorer queries, teams with a league game since the newest stored
  `last_match_time` (team_rating) and then their names, tags and logos (teams, TEAM_IDS_PER_QUERY ids per query).
  A team renamed without playing a league game keeps its old name until it plays.
"""

import sqlite3
import threading
import time
from typing import Any, Optional

from flask import Flask
from werkzeug.serving import is_running_from_reloader

from backend.logging_config import setup_logging
from backend.opendota import OpenDotaError, get_json
from backend.pro_players import fetch_teams_from_api, get_d2ba_db, store_teams

logger = setup_logging(__name__)

TEAMS_SYNC_NAME = "teams"  # sync_state.name of the teams list
TEAMS_MAX_AGE_SECONDS = 24 * 60 * 60  # Older teams data is obsolete
RETRY_AFTER_FAILURE_SECONDS = 10 * 60  # No new automatic sync this soon after a failed one
TEAM_IDS_PER_QUERY = 200  # Team ids in one explorer `team_id IN (...)` query

_sync_lock = threading.Lock()
_last_failure: Optional[float] = None  # Time of the last failed automatic sync in this process


class TeamsSyncRunningError(Exception):
    """A teams sync is already running (from POST /api/teams/sync or an automatic one)."""


def get_teams_synced_at() -> Optional[int]:
    """Time of the last successful teams sync.

    Returns:
        Unix seconds, or None when the teams list was never synced
    """
    row = get_d2ba_db().execute("SELECT synced_at FROM sync_state WHERE name = ?", (TEAMS_SYNC_NAME,)).fetchone()
    return row["synced_at"] if row else None


def is_teams_sync_due(now: Optional[float] = None) -> bool:
    """Whether the teams data is obsolete: never synced or the last sync is 24+ hours old.

    Args:
        now: Current unix time (defaults to time.time())

    Returns:
        True when a sync is needed
    """
    synced_at = get_teams_synced_at()
    current = time.time() if now is None else now
    return synced_at is None or current - synced_at >= TEAMS_MAX_AGE_SECONDS


def _newest_match_time() -> Optional[int]:
    """Newest stored team `last_match_time`, the start of an incremental sync (None when no team has one)."""
    row = get_d2ba_db().execute("SELECT MAX(last_match_time) FROM teams").fetchone()
    return row[0] if row else None


def _explorer_rows(sql: str) -> list[dict[str, Any]]:
    """Rows of one OpenDota explorer query.

    Raises:
        ConnectionError: If OpenDota could not be reached
        ValueError: If the answer has no rows (e.g. a query error)
    """
    try:
        payload = get_json("/explorer", params={"sql": sql}, timeout=30)
    except OpenDotaError as e:
        raise ConnectionError(f"Failed to query OpenDota explorer: {e}") from e
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        error = payload.get("err") if isinstance(payload, dict) else None
        raise ValueError(f"Invalid OpenDota explorer answer: {error or 'no rows'}")
    return [row for row in rows if isinstance(row, dict)]


def fetch_recent_teams(since: int) -> list[dict[str, Any]]:
    """Teams with a league game at or after `since`, in the `/teams` format.

    The explorer refuses joins of teams and team_rating, so ratings and names come from separate queries.

    Args:
        since: Unix time

    Returns:
        Team dictionaries (team_id, rating, name, tag, logo_url, last_match_time); teams OpenDota has no
        name row for are left out

    Raises:
        ConnectionError: If OpenDota could not be reached
        ValueError: If an explorer answer is invalid
    """
    ratings = _explorer_rows(
        f"SELECT team_id, rating, last_match_time FROM team_rating WHERE last_match_time >= {int(since)}"
    )
    by_id = {row["team_id"]: row for row in ratings if isinstance(row.get("team_id"), int)}
    ids = list(by_id)
    teams: list[dict[str, Any]] = []
    for start in range(0, len(ids), TEAM_IDS_PER_QUERY):
        batch = ",".join(str(team_id) for team_id in ids[start : start + TEAM_IDS_PER_QUERY])
        for row in _explorer_rows(f"SELECT team_id, name, tag, logo_url FROM teams WHERE team_id IN ({batch})"):
            rating = by_id.get(row.get("team_id"))
            if rating is not None:
                teams.append({**row, "rating": rating.get("rating"), "last_match_time": rating.get("last_match_time")})
    return teams


def run_teams_sync(full: bool = False) -> int:
    """Update the teams list and record the sync time.

    Incremental unless `full` is set or the teams table is empty. A full sync records the time only when teams
    were stored; an incremental one also when nothing changed.

    Args:
        full: Fetch every `/teams` page

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
        since = None if full else _newest_match_time()
        if since is None:
            count = store_teams(fetch_teams_from_api())
            if not count:
                return 0
        else:
            count = store_teams(fetch_recent_teams(since))
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
    global _last_failure
    try:
        with app.app_context():
            count = run_teams_sync()
            logger.info(f"Automatic teams sync stored {count} teams")
    except TeamsSyncRunningError:
        logger.info("Automatic teams sync skipped, a sync is already running")
    except Exception as e:
        _last_failure = time.time()
        logger.error(f"Error in automatic teams sync: {e}")


def sync_teams_if_obsolete(app: Flask) -> Optional[threading.Thread]:
    """Start a background teams sync when the data is obsolete, without blocking the caller.

    Skipped while a sync is running and for RETRY_AFTER_FAILURE_SECONDS after a failed one.

    Args:
        app: Flask app

    Returns:
        The started thread, or None when no sync is needed
    """
    if _sync_lock.locked():
        return None
    if _last_failure is not None and time.time() - _last_failure < RETRY_AFTER_FAILURE_SECONDS:
        return None
    try:
        with app.app_context():
            if not is_teams_sync_due():
                return None
    except sqlite3.Error as e:
        logger.error(f"Error checking teams sync time: {e}")
        return None
    logger.info("Teams data is older than 24 hours or was never synced, syncing in the background")
    thread = threading.Thread(target=_sync_in_background, args=(app,), name="teams-sync", daemon=True)
    thread.start()
    return thread


def sync_teams_on_startup(app: Flask) -> Optional[threading.Thread]:
    """Start a background teams sync at startup when the data is obsolete.

    With the debug reloader, only the serving child process syncs (the watching parent also creates the app).

    Args:
        app: Flask app

    Returns:
        The started thread, or None when no sync is needed
    """
    if app.debug and not is_running_from_reloader():
        return None
    return sync_teams_if_obsolete(app)

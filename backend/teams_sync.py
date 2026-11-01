"""Teams list sync from OpenDota into d2ba.sqlite (used by team search and the Matches tab).

The list is updated on its own by the `teams` cache job (backend.jobs) when the last sync is 24+ hours old, or on
demand by POST /api/teams/sync. One sync runs at a time in a process.

- Full sync (teams table empty, or POST /api/teams/sync?full=1): every `/teams` page, about 22 requests.
- Incremental sync (otherwise): two explorer queries, teams with a league game since the newest stored
  `last_match_time` (team_rating) and then their names, tags and logos (teams, TEAM_IDS_PER_QUERY ids per query).
  A team renamed without playing a league game keeps its old name until it plays.
"""

import threading
import time
from typing import Any, Optional

from backend.opendota import OpenDotaError, get_json
from backend.pro_players import fetch_teams_from_api, get_d2ba_db, store_teams

TEAMS_SYNC_NAME = "teams"  # sync_state.name of the teams list
TEAM_IDS_PER_QUERY = 200  # Team ids in one explorer `team_id IN (...)` query

_sync_lock = threading.Lock()


class TeamsSyncRunningError(Exception):
    """A teams sync is already running in this process."""


def get_teams_synced_at() -> Optional[int]:
    """Time of the last successful teams sync.

    Returns:
        Unix seconds, or None when the teams list was never synced
    """
    row = get_d2ba_db().execute("SELECT synced_at FROM sync_state WHERE name = ?", (TEAMS_SYNC_NAME,)).fetchone()
    return row["synced_at"] if row else None


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
        payload = get_json("/explorer", params={"sql": sql}, timeout=30, background=True)
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

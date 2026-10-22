"""Team statistics snapshots: what the Compare page showed for a team, saved in predictions.sqlite.

A snapshot is identified by team + UTC day + days window + the team's latest league match. The data only changes
when the team plays, the window changes or the day changes, so saving the same key again refreshes the stored row
(pub matches and ranks still move during the day) instead of adding a new one. Once a prediction uses a snapshot it
is locked: saving its key again returns it unchanged.
"""

import json
import sqlite3
import time
from datetime import UTC, date, datetime
from typing import Any, Optional

from backend.predictions_db import get_predictions_db

# Columns returned for a snapshot, without its data; team_name is read from the stored team
_SUMMARY_COLUMNS = (
    "snapshot_id, team_id, json_extract(data, '$.team.team') AS team_name, snapshot_date, days, last_match_time, "
    "taken_at, app_version"
)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a snapshot row to a response dict, parsing `data` when it was selected."""
    result = dict(row)
    if "data" in result:
        result["data"] = json.loads(result["data"])
    return result


def save_snapshot(
    team_id: int,
    days: int,
    team: dict[str, Any],
    summary: Optional[dict[str, Any]],
    players: list[dict[str, Any]],
    app_version: str,
) -> tuple[dict[str, Any], bool]:
    """Save a team snapshot, or refresh the one with the same team, day, window and latest league match.

    A snapshot already used by a prediction is not refreshed and is returned as it is.

    Args:
        team_id: Team the snapshot belongs to
        days: Statistics window the data was computed with
        team: The team entry of /api/statistics as shown (task_id is dropped)
        summary: The player match summary of /api/results, or None when it was not available
        players: Per player account_id, rank and match_count from /api/results
        app_version: Backend version that produced the data

    Returns:
        The saved snapshot without its data, and True when a new snapshot was created (False when refreshed)
    """
    now = int(time.time())
    snapshot_date = datetime.fromtimestamp(now, UTC).strftime("%Y-%m-%d")
    last_match_time = team.get("latest_match_time") or 0
    stored_team = {key: value for key, value in team.items() if key != "task_id"}
    data = json.dumps({"team": stored_team, "summary": summary, "players": players})
    key = (team_id, snapshot_date, days, last_match_time)

    db = get_predictions_db()
    existing = db.execute(
        "SELECT snapshot_id FROM team_snapshots "
        "WHERE team_id = ? AND snapshot_date = ? AND days = ? AND last_match_time = ?",
        key,
    ).fetchone()
    if existing:
        snapshot_id = existing["snapshot_id"]
        if not is_snapshot_used(snapshot_id):
            db.execute(
                "UPDATE team_snapshots SET taken_at = ?, app_version = ?, data = ? WHERE snapshot_id = ?",
                (now, app_version, data, snapshot_id),
            )
    else:
        cursor = db.execute(
            "INSERT INTO team_snapshots (team_id, snapshot_date, days, last_match_time, taken_at, app_version, data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (*key, now, app_version, data),
        )
        snapshot_id = cursor.lastrowid
    db.commit()

    row = db.execute(f"SELECT {_SUMMARY_COLUMNS} FROM team_snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
    return _row_to_dict(row), existing is None


def is_snapshot_used(snapshot_id: int) -> bool:
    """Check whether a prediction points at the snapshot (then its data is locked).

    Args:
        snapshot_id: Snapshot to check

    Returns:
        True when at least one prediction uses the snapshot
    """
    row = (
        get_predictions_db()
        .execute(
            "SELECT 1 FROM predictions WHERE team1_snapshot_id = ? OR team2_snapshot_id = ? LIMIT 1",
            (snapshot_id, snapshot_id),
        )
        .fetchone()
    )
    return row is not None


def list_snapshots(
    team_id: Optional[int] = None, date_from: Optional[date] = None, date_to: Optional[date] = None
) -> list[dict[str, Any]]:
    """List snapshots without their data, newest first.

    Args:
        team_id: Only this team's snapshots
        date_from: Only snapshots from this UTC day on
        date_to: Only snapshots up to this UTC day (inclusive)

    Returns:
        Snapshots as dicts
    """
    conditions: list[str] = []
    params: list[Any] = []
    if team_id is not None:
        conditions.append("team_id = ?")
        params.append(team_id)
    if date_from is not None:
        conditions.append("snapshot_date >= ?")
        params.append(date_from.isoformat())
    if date_to is not None:
        conditions.append("snapshot_date <= ?")
        params.append(date_to.isoformat())
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    rows = get_predictions_db().execute(
        f"SELECT {_SUMMARY_COLUMNS} FROM team_snapshots {where} ORDER BY taken_at DESC, snapshot_id DESC", params
    )
    return [_row_to_dict(row) for row in rows]


def get_snapshot(snapshot_id: int) -> Optional[dict[str, Any]]:
    """Get one snapshot with its data.

    Args:
        snapshot_id: Snapshot to read

    Returns:
        The snapshot, or None when it does not exist
    """
    row = (
        get_predictions_db()
        .execute(f"SELECT {_SUMMARY_COLUMNS}, data FROM team_snapshots WHERE snapshot_id = ?", (snapshot_id,))
        .fetchone()
    )
    return _row_to_dict(row) if row else None

"""Prediction log: series-win bets made from two team snapshots, saved in predictions.sqlite.

Odds, series format, bet, stake and comment can be edited after saving, and so can the review (maps won by each team
and a review note). The snapshots stay as saved. Whether the bet won is computed from the stored values, not stored.
"""

import json
import sqlite3
import time
from typing import Any, Optional

from backend.predictions_db import get_predictions_db
from backend.snapshots import get_snapshot

# Prediction columns plus each team's name, tag and logo as saved in its snapshot
_LIST_QUERY = """
    SELECT p.*,
        s1.team_id AS team1_id, s1.data AS team1_data,
        s2.team_id AS team2_id, s2.data AS team2_data
    FROM predictions p
    JOIN team_snapshots s1 ON s1.snapshot_id = p.team1_snapshot_id
    JOIN team_snapshots s2 ON s2.snapshot_id = p.team2_snapshot_id
"""

_STATUS_CONDITIONS = {
    "pending": "p.team1_maps_won IS NULL",
    "settled": "p.team1_maps_won IS NOT NULL",
}


class SnapshotMissingError(LookupError):
    """A prediction refers to a snapshot that does not exist."""

    def __init__(self, snapshot_id: int) -> None:
        """Remember which snapshot is missing."""
        super().__init__(f"Snapshot {snapshot_id} not found")
        self.snapshot_id = snapshot_id


def is_valid_result(best_of: Optional[int], team1_maps_won: int, team2_maps_won: int) -> bool:
    """Check that a map score is a finished series of the given format.

    bo1/bo3/bo5: one team won (best_of + 1) / 2 maps and the other fewer. bo2: both maps were played (2-0, 1-1, 0-2).
    Unknown format: any score with at least one map played.

    Args:
        best_of: Series format (1, 2, 3 or 5), None when unknown
        team1_maps_won: Maps won by team 1
        team2_maps_won: Maps won by team 2

    Returns:
        True when the score can be the final result of the series
    """
    if team1_maps_won < 0 or team2_maps_won < 0:
        return False
    if best_of is None:
        return team1_maps_won + team2_maps_won > 0
    if best_of == 2:
        return team1_maps_won + team2_maps_won == 2
    to_win = (best_of + 1) // 2
    return max(team1_maps_won, team2_maps_won) == to_win and min(team1_maps_won, team2_maps_won) < to_win


def series_winner(team1_maps_won: Optional[int], team2_maps_won: Optional[int]) -> Optional[int]:
    """Team (1 or 2) that won the series, None while pending or for a bo2 draw."""
    if team1_maps_won is None or team2_maps_won is None or team1_maps_won == team2_maps_won:
        return None
    return 1 if team1_maps_won > team2_maps_won else 2


def bet_won(prediction: dict[str, Any]) -> Optional[bool]:
    """Compute whether the bet team won the series. A draw (bo2 1-1) loses a series-win bet.

    Args:
        prediction: Row with bet_team and maps won

    Returns:
        True or False, None while pending or without a bet
    """
    bet_team = prediction["bet_team"]
    if bet_team is None or prediction["team1_maps_won"] is None:
        return None
    return bool(series_winner(prediction["team1_maps_won"], prediction["team2_maps_won"]) == bet_team)


def _team_info(snapshot_id: int, team_id: int, data: str) -> dict[str, Any]:
    """Team name, tag and logo as saved in the snapshot."""
    team = json.loads(data).get("team") or {}
    return {
        "snapshot_id": snapshot_id,
        "team_id": team_id,
        "name": team.get("team"),
        "tag": team.get("tag"),
        "logo_url": team.get("logo_url"),
    }


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a joined prediction row to a response dict with computed bet_won."""
    raw = dict(row)
    prediction = {
        "prediction_id": raw["prediction_id"],
        "created_at": raw["created_at"],
        "team1": _team_info(raw["team1_snapshot_id"], raw["team1_id"], raw["team1_data"]),
        "team2": _team_info(raw["team2_snapshot_id"], raw["team2_id"], raw["team2_data"]),
        "team1_odds": raw["team1_odds"],
        "team2_odds": raw["team2_odds"],
        "best_of": raw["best_of"],
        "bet_team": raw["bet_team"],
        "stake": raw["stake"],
        "comment": raw["comment"],
        "team1_maps_won": raw["team1_maps_won"],
        "team2_maps_won": raw["team2_maps_won"],
        "review_note": raw["review_note"],
    }
    prediction["bet_won"] = bet_won(prediction)
    return prediction


def _fetch(prediction_id: int) -> Optional[dict[str, Any]]:
    """Read one prediction without its snapshots' data."""
    row = get_predictions_db().execute(f"{_LIST_QUERY} WHERE p.prediction_id = ?", (prediction_id,)).fetchone()
    return _row_to_dict(row) if row else None


def create_prediction(
    team1_snapshot_id: int,
    team2_snapshot_id: int,
    team1_odds: float,
    team2_odds: float,
    best_of: Optional[int],
    bet_team: Optional[int],
    stake: Optional[float],
    comment: str,
) -> dict[str, Any]:
    """Save a prediction. Its two snapshots are locked from then on.

    Args:
        team1_snapshot_id: Snapshot of team 1
        team2_snapshot_id: Snapshot of team 2
        team1_odds: Bookmaker decimal coefficient for team 1
        team2_odds: Bookmaker decimal coefficient for team 2
        best_of: Series format (1, 2, 3 or 5), None when unknown
        bet_team: Team bet on to win the series (1 or 2), None for a prediction without a bet
        stake: Amount bet, None if not given
        comment: Reasoning

    Returns:
        The saved prediction

    Raises:
        SnapshotMissingError: When a snapshot does not exist
    """
    db = get_predictions_db()
    for snapshot_id in (team1_snapshot_id, team2_snapshot_id):
        if db.execute("SELECT 1 FROM team_snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone() is None:
            raise SnapshotMissingError(snapshot_id)
    cursor = db.execute(
        "INSERT INTO predictions (created_at, team1_snapshot_id, team2_snapshot_id, team1_odds, team2_odds, best_of, "
        "bet_team, stake, comment) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            int(time.time()),
            team1_snapshot_id,
            team2_snapshot_id,
            team1_odds,
            team2_odds,
            best_of,
            bet_team,
            stake,
            comment,
        ),
    )
    db.commit()
    prediction = _fetch(cursor.lastrowid or 0)
    assert prediction is not None
    return prediction


def list_predictions(status: Optional[str] = None) -> list[dict[str, Any]]:
    """List predictions, newest first.

    Args:
        status: "pending" (no result yet), "settled" (result entered) or None for all

    Returns:
        Predictions with team names and logos, without the snapshots' data
    """
    where = f"WHERE {_STATUS_CONDITIONS[status]}" if status else ""
    rows = get_predictions_db().execute(f"{_LIST_QUERY} {where} ORDER BY p.created_at DESC, p.prediction_id DESC")
    return [_row_to_dict(row) for row in rows]


def get_prediction(prediction_id: int) -> Optional[dict[str, Any]]:
    """Get one prediction with both snapshots and their data, for the review page.

    Args:
        prediction_id: Prediction to read

    Returns:
        The prediction with team1_snapshot and team2_snapshot, or None when it does not exist
    """
    prediction = _fetch(prediction_id)
    if prediction is None:
        return None
    prediction["team1_snapshot"] = get_snapshot(prediction["team1"]["snapshot_id"])
    prediction["team2_snapshot"] = get_snapshot(prediction["team2"]["snapshot_id"])
    return prediction


def save_review(
    prediction_id: int, team1_maps_won: int, team2_maps_won: int, review_note: Optional[str]
) -> Optional[dict[str, Any]]:
    """Save the actual result and the review note. The result must be valid for the series format.

    Args:
        prediction_id: Prediction to review
        team1_maps_won: Maps won by team 1
        team2_maps_won: Maps won by team 2
        review_note: Thoughts after the match, None keeps the saved note

    Returns:
        The updated prediction, or None when it does not exist

    Raises:
        ValueError: When the score is not a finished series of the prediction's format
    """
    prediction = _fetch(prediction_id)
    if prediction is None:
        return None
    if not is_valid_result(prediction["best_of"], team1_maps_won, team2_maps_won):
        raise ValueError(
            f"{team1_maps_won}-{team2_maps_won} is not a result of a bo{prediction['best_of'] or '?'} series"
        )
    db = get_predictions_db()
    db.execute(
        "UPDATE predictions SET team1_maps_won = ?, team2_maps_won = ?, review_note = COALESCE(?, review_note) "
        "WHERE prediction_id = ?",
        (team1_maps_won, team2_maps_won, review_note, prediction_id),
    )
    db.commit()
    return _fetch(prediction_id)


def update_decision(
    prediction_id: int,
    team1_odds: float,
    team2_odds: float,
    best_of: Optional[int],
    bet_team: Optional[int],
    stake: Optional[float],
    comment: str,
) -> Optional[dict[str, Any]]:
    """Replace the bookmaker values and the decision of a saved prediction. Its snapshots and review stay.

    Args:
        prediction_id: Prediction to edit
        team1_odds: Bookmaker decimal coefficient for team 1
        team2_odds: Bookmaker decimal coefficient for team 2
        best_of: Series format (1, 2, 3 or 5), None when unknown
        bet_team: Team bet on to win the series (1 or 2), None for a prediction without a bet
        stake: Amount bet, None if not given
        comment: Reasoning

    Returns:
        The updated prediction, or None when it does not exist

    Raises:
        ValueError: When the saved result is not a finished series of the new format
    """
    prediction = _fetch(prediction_id)
    if prediction is None:
        return None
    score = (prediction["team1_maps_won"], prediction["team2_maps_won"])
    if score[0] is not None and not is_valid_result(best_of, *score):
        raise ValueError(f"Saved result {score[0]}-{score[1]} is not a result of a bo{best_of or '?'} series")
    db = get_predictions_db()
    db.execute(
        "UPDATE predictions SET team1_odds = ?, team2_odds = ?, best_of = ?, bet_team = ?, stake = ?, comment = ? "
        "WHERE prediction_id = ?",
        (team1_odds, team2_odds, best_of, bet_team, stake, comment, prediction_id),
    )
    db.commit()
    return _fetch(prediction_id)


def delete_prediction(prediction_id: int) -> bool:
    """Delete a prediction made by mistake. Its snapshots stay.

    Args:
        prediction_id: Prediction to delete

    Returns:
        True when it existed
    """
    db = get_predictions_db()
    cursor = db.execute("DELETE FROM predictions WHERE prediction_id = ?", (prediction_id,))
    db.commit()
    return cursor.rowcount > 0

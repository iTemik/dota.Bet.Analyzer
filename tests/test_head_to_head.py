"""Tests for GET /api/predictions/{id}/head-to-head."""

import sqlite3
from unittest.mock import MagicMock, patch

from backend.rosters import DAY_SECONDS
from tests.test_predictions import (  # noqa: F401
    post_prediction,
    prediction_body,
    snapshots,
)
from tests.test_snapshots import DAY1

CREATED_AT = DAY1 + 600


def team_match(match_id: int, start_time: int, opponent: int, radiant: bool = True, radiant_win: bool = True) -> dict:
    """A /teams/{id}/matches row."""
    return {
        "match_id": match_id,
        "start_time": start_time,
        "leagueid": 1,
        "radiant": radiant,
        "radiant_win": radiant_win,
        "opposing_team_id": opponent,
    }


def get_head_to_head(client, prediction_id: int, rows: list[dict]):
    """GET the head-to-head with OpenDota mocked; returns the response and the mocked requests.get."""
    response = MagicMock(status_code=200)
    response.json.return_value = rows
    with (
        patch("backend.opendota.requests.get", return_value=response) as get,
        patch("backend.head_to_head.time.time", return_value=CREATED_AT + DAY_SECONDS),
    ):
        return client.get(f"/api/predictions/{prediction_id}/head-to-head"), get


def test_lists_matches_against_team2_in_window(client, snapshots):  # noqa: F811
    prediction_id = post_prediction(client, prediction_body(snapshots), now=CREATED_AT).get_json()["prediction_id"]
    rows = [
        team_match(5, CREATED_AT + 3600, opponent=202, radiant=False, radiant_win=True),
        team_match(4, CREATED_AT - 3600, opponent=202),
        team_match(3, CREATED_AT - 2 * DAY_SECONDS, opponent=303),
        team_match(2, CREATED_AT - 21 * DAY_SECONDS, opponent=202),
    ]

    response, get = get_head_to_head(client, prediction_id, rows)

    assert response.status_code == 200
    assert response.get_json() == {
        "since": CREATED_AT - 20 * DAY_SECONDS,
        "matches": [
            {"match_id": 5, "start_time": CREATED_AT + 3600, "team1_won": False, "before_prediction": False},
            {"match_id": 4, "start_time": CREATED_AT - 3600, "team1_won": True, "before_prediction": True},
        ],
    }
    assert get.call_count == 1
    assert get.call_args.args[0].endswith("/teams/101/matches")


def test_second_call_uses_cached_team_matches(client, snapshots):  # noqa: F811
    prediction_id = post_prediction(client, prediction_body(snapshots), now=CREATED_AT).get_json()["prediction_id"]
    rows = [team_match(4, CREATED_AT - 3600, opponent=202)]

    get_head_to_head(client, prediction_id, rows)
    response, get = get_head_to_head(client, prediction_id, rows)

    assert len(response.get_json()["matches"]) == 1
    assert get.call_count == 0


def test_no_matches(client, snapshots):  # noqa: F811
    prediction_id = post_prediction(client, prediction_body(snapshots), now=CREATED_AT).get_json()["prediction_id"]

    response, _ = get_head_to_head(client, prediction_id, [])

    assert response.status_code == 200
    assert response.get_json()["matches"] == []


def test_unknown_prediction_returns_404(client):
    response, get = get_head_to_head(client, 12345, [])

    assert response.status_code == 404
    assert response.get_json()["code"] == "PREDICTION_NOT_FOUND"
    assert get.call_count == 0


def test_database_error_returns_500(client):
    with patch("backend.dota_bet_analyzer.get_head_to_head", side_effect=sqlite3.OperationalError("locked")):
        response = client.get("/api/predictions/1/head-to-head")

    assert response.status_code == 500
    assert response.get_json()["code"] == "FAILED_TO_READ_PREDICTIONS"

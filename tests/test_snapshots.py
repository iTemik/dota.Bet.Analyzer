"""Tests for team statistics snapshots: /api/snapshots endpoints and the predictions database."""

import sqlite3
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

DAY1 = int(datetime(2026, 10, 21, 12, 0, tzinfo=UTC).timestamp())
DAY2 = int(datetime(2026, 10, 22, 9, 30, tzinfo=UTC).timestamp())
MATCH_TIME = 1761000000


def snapshot_body(team_id: int = 101, days: int = 20, latest_match_time: int | None = MATCH_TIME, **team) -> dict:
    """Build a POST /api/snapshots body as the Compare page would send it."""
    return {
        "team_id": team_id,
        "days": days,
        "team": {
            "team_id": team_id,
            "team": f"Team {team_id}",
            "tag": "T",
            "rating": 1500.0,
            "task_id": "task_1",
            "players": [{"name": "ID 1", "id": 1, "games": 10, "is_core": True}],
            "roster_state": "stable",
            "latest_match_time": latest_match_time,
            **team,
        },
        "summary": {"rating_matches": 12, "avg_rank": 80.5, "bad_rank_players": 1},
        "players": [{"account_id": 1, "rank": 80, "match_count": 30}],
    }


def post_snapshot(client, body: dict, now: int = DAY1):
    """POST a snapshot with the clock set to `now`."""
    with patch("backend.snapshots.time.time", return_value=now):
        return client.post("/api/snapshots", json=body)


class TestCreateSnapshot:
    """POST /api/snapshots."""

    def test_creates_snapshot(self, client):
        response = post_snapshot(client, snapshot_body())

        assert response.status_code == 201
        data = response.get_json()
        assert data["snapshot_id"] > 0
        assert data["team_id"] == 101
        assert data["team_name"] == "Team 101"
        assert data["snapshot_date"] == "2026-10-21"
        assert data["days"] == 20
        assert data["last_match_time"] == MATCH_TIME
        assert data["taken_at"] == DAY1
        assert data["app_version"]
        assert "data" not in data

    def test_stores_data_without_task_id(self, client):
        snapshot_id = post_snapshot(client, snapshot_body()).get_json()["snapshot_id"]

        data = client.get(f"/api/snapshots/{snapshot_id}").get_json()["data"]

        expected_team = {key: value for key, value in snapshot_body()["team"].items() if key != "task_id"}
        assert data["team"] == expected_team
        assert data["summary"] == {"rating_matches": 12, "avg_rank": 80.5, "bad_rank_players": 1}
        assert data["players"] == [{"account_id": 1, "rank": 80, "match_count": 30}]

    def test_same_key_refreshes_existing_snapshot(self, client):
        first = post_snapshot(client, snapshot_body(rating=1500.0), now=DAY1).get_json()

        response = post_snapshot(client, snapshot_body(rating=1600.0), now=DAY1 + 3600)

        assert response.status_code == 200
        refreshed = response.get_json()
        assert refreshed["snapshot_id"] == first["snapshot_id"]
        assert refreshed["taken_at"] == DAY1 + 3600
        stored = client.get(f"/api/snapshots/{first['snapshot_id']}").get_json()
        assert stored["data"]["team"]["rating"] == 1600.0
        assert len(client.get("/api/snapshots").get_json()) == 1

    @pytest.mark.parametrize(
        ("change", "now"),
        [
            ({"latest_match_time": MATCH_TIME + 7200}, DAY1),  # the team played again
            ({}, DAY2),  # another day
            ({"days": 30}, DAY1),  # another window
            ({"team_id": 202}, DAY1),  # another team
        ],
    )
    def test_new_key_creates_new_snapshot(self, client, change, now):
        first = post_snapshot(client, snapshot_body()).get_json()

        response = post_snapshot(client, snapshot_body(**change), now=now)

        assert response.status_code == 201
        assert response.get_json()["snapshot_id"] != first["snapshot_id"]

    def test_team_without_league_match_uses_zero(self, client):
        response = post_snapshot(client, snapshot_body(latest_match_time=None))

        assert response.status_code == 201
        assert response.get_json()["last_match_time"] == 0

    def test_summary_and_players_are_optional(self, client):
        body = snapshot_body()
        del body["summary"]
        del body["players"]

        snapshot_id = post_snapshot(client, body).get_json()["snapshot_id"]

        data = client.get(f"/api/snapshots/{snapshot_id}").get_json()["data"]
        assert data["summary"] is None
        assert data["players"] == []

    @pytest.mark.parametrize("missing", ["team_id", "days", "team"])
    def test_missing_field_returns_422(self, client, missing):
        body = snapshot_body()
        del body[missing]

        response = post_snapshot(client, body)

        assert response.status_code == 422
        assert response.get_json()["status"] == 422

    @pytest.mark.parametrize(
        ("field", "value"), [("team_id", "abc"), ("team_id", 0), ("days", 0), ("days", 366), ("team", [1, 2])]
    )
    def test_invalid_field_returns_422(self, client, field, value):
        body = snapshot_body()
        body[field] = value

        assert post_snapshot(client, body).status_code == 422

    def test_player_without_account_id_returns_422(self, client):
        body = snapshot_body()
        body["players"] = [{"rank": 5}]

        assert post_snapshot(client, body).status_code == 422

    def test_team_id_mismatch_returns_422(self, client):
        body = snapshot_body()
        body["team"]["team_id"] = 999

        response = post_snapshot(client, body)

        assert response.status_code == 422
        assert response.get_json()["code"] == "TEAM_ID_MISMATCH"

    def test_database_error_returns_500(self, client):
        with patch("backend.dota_bet_analyzer.save_snapshot", side_effect=sqlite3.OperationalError("locked")):
            response = client.post("/api/snapshots", json=snapshot_body())

        assert response.status_code == 500
        assert response.get_json()["code"] == "FAILED_TO_STORE_SNAPSHOT"


class TestListSnapshots:
    """GET /api/snapshots."""

    @pytest.fixture
    def saved(self, client):
        """Three snapshots: team 101 on day 1 and day 2, team 202 on day 2."""
        return [
            post_snapshot(client, snapshot_body(101), now=DAY1).get_json()["snapshot_id"],
            post_snapshot(client, snapshot_body(101), now=DAY2).get_json()["snapshot_id"],
            post_snapshot(client, snapshot_body(202), now=DAY2 + 60).get_json()["snapshot_id"],
        ]

    def test_lists_newest_first_without_data(self, client, saved):
        response = client.get("/api/snapshots")

        assert response.status_code == 200
        snapshots = response.get_json()
        assert [s["snapshot_id"] for s in snapshots] == list(reversed(saved))
        assert all("data" not in s for s in snapshots)
        assert snapshots[0]["team_name"] == "Team 202"

    def test_filters_by_team(self, client, saved):
        snapshots = client.get("/api/snapshots?team_id=101").get_json()

        assert [s["snapshot_id"] for s in snapshots] == [saved[1], saved[0]]

    def test_filters_by_date_range(self, client, saved):
        assert [s["snapshot_id"] for s in client.get("/api/snapshots?from=2026-10-22").get_json()] == [
            saved[2],
            saved[1],
        ]
        assert [s["snapshot_id"] for s in client.get("/api/snapshots?to=2026-10-21").get_json()] == [saved[0]]
        assert client.get("/api/snapshots?team_id=202&from=2026-10-21&to=2026-10-21").get_json() == []

    def test_empty_list(self, client):
        response = client.get("/api/snapshots")

        assert response.status_code == 200
        assert response.get_json() == []

    @pytest.mark.parametrize("query", ["team_id=abc", "from=yesterday", "to=2026-13-01"])
    def test_invalid_query_returns_422(self, client, query):
        assert client.get(f"/api/snapshots?{query}").status_code == 422

    def test_database_error_returns_500(self, client):
        with patch("backend.dota_bet_analyzer.list_snapshots", side_effect=sqlite3.OperationalError("locked")):
            response = client.get("/api/snapshots")

        assert response.status_code == 500
        assert response.get_json()["code"] == "FAILED_TO_READ_SNAPSHOTS"


class TestGetSnapshot:
    """GET /api/snapshots/{id}."""

    def test_returns_snapshot_with_data(self, client):
        snapshot_id = post_snapshot(client, snapshot_body()).get_json()["snapshot_id"]

        response = client.get(f"/api/snapshots/{snapshot_id}")

        assert response.status_code == 200
        data = response.get_json()
        assert data["snapshot_id"] == snapshot_id
        assert data["team_name"] == "Team 101"
        assert set(data["data"]) == {"team", "summary", "players"}

    def test_unknown_id_returns_404(self, client):
        response = client.get("/api/snapshots/12345")

        assert response.status_code == 404
        assert response.get_json()["code"] == "SNAPSHOT_NOT_FOUND"

    def test_database_error_returns_500(self, client):
        with patch("backend.dota_bet_analyzer.get_snapshot", side_effect=sqlite3.OperationalError("locked")):
            response = client.get("/api/snapshots/1")

        assert response.status_code == 500


class TestPredictionsDatabase:
    """predictions.sqlite is separate from the d2ba cache."""

    def test_snapshot_goes_to_predictions_db_only(self, app, client):
        post_snapshot(client, snapshot_body())

        predictions = sqlite3.connect(f"{app.instance_path}/predictions.sqlite")
        d2ba = sqlite3.connect(f"{app.instance_path}/d2ba.sqlite")
        try:
            assert predictions.execute("SELECT COUNT(*) FROM team_snapshots").fetchone()[0] == 1
            d2ba_tables = {row[0] for row in d2ba.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            assert "team_snapshots" not in d2ba_tables
        finally:
            predictions.close()
            d2ba.close()

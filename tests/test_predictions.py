"""Tests for the prediction log: /api/predictions endpoints, result validation and snapshot locking."""

import sqlite3
from unittest.mock import patch

import pytest

from backend.predictions import bet_outcome, is_valid_result
from tests.test_snapshots import DAY1, post_snapshot, snapshot_body


@pytest.fixture
def snapshots(client):
    """Snapshot ids of team 101 and team 202."""
    return (
        post_snapshot(client, snapshot_body(101, logo_url="https://logo/101.png")).get_json()["snapshot_id"],
        post_snapshot(client, snapshot_body(202)).get_json()["snapshot_id"],
    )


def prediction_body(snapshots: tuple[int, int], **changes) -> dict:
    """Build a POST /api/predictions body as the Compare page would send it."""
    return {
        "team1_snapshot_id": snapshots[0],
        "team2_snapshot_id": snapshots[1],
        "team1_odds": 1.85,
        "team2_odds": 2.05,
        "best_of": 3,
        "bet_team": 1,
        "stake": 100,
        "comment": "Stable core, stand-ins on the other side",
        **changes,
    }


def post_prediction(client, body: dict, now: int = DAY1 + 600):
    """POST a prediction with the clock set to `now`."""
    with patch("backend.predictions.time.time", return_value=now):
        return client.post("/api/predictions", json=body)


class TestCreatePrediction:
    """POST /api/predictions."""

    def test_creates_prediction(self, client, snapshots):
        response = post_prediction(client, prediction_body(snapshots))

        assert response.status_code == 201
        data = response.get_json()
        assert data["prediction_id"] > 0
        assert data["created_at"] == DAY1 + 600
        assert data["team1"] == {
            "snapshot_id": snapshots[0],
            "team_id": 101,
            "name": "Team 101",
            "tag": "T",
            "logo_url": "https://logo/101.png",
        }
        assert data["team2"]["team_id"] == 202
        assert (data["team1_odds"], data["team2_odds"], data["best_of"]) == (1.85, 2.05, 3)
        assert (data["bet_team"], data["stake"]) == (1, 100)
        assert data["comment"] == "Stable core, stand-ins on the other side"
        assert data["team1_maps_won"] is None and data["team2_maps_won"] is None
        assert data["bet_won"] is None and data["profit"] is None

    def test_prediction_without_bet(self, client, snapshots):
        body = prediction_body(snapshots, bet_team=None, stake=None)
        del body["comment"]

        data = post_prediction(client, body).get_json()

        assert data["bet_team"] is None
        assert data["stake"] is None
        assert data["comment"] == ""

    def test_unknown_snapshot_returns_404(self, client, snapshots):
        response = post_prediction(client, prediction_body((snapshots[0], 9999)))

        assert response.status_code == 404
        assert response.get_json()["code"] == "SNAPSHOT_NOT_FOUND"
        assert response.get_json()["details"]["snapshot_id"] == 9999

    @pytest.mark.parametrize(
        "changes",
        [
            {"team1_odds": 1.0},
            {"team2_odds": 0.5},
            {"best_of": 4},
            {"best_of": 7},
            {"bet_team": 3},
            {"bet_team": None, "stake": 50},
            {"stake": 0},
            {"team1_odds": "abc"},
        ],
    )
    def test_invalid_body_returns_422(self, client, snapshots, changes):
        assert post_prediction(client, prediction_body(snapshots, **changes)).status_code == 422

    def test_same_snapshot_for_both_teams_returns_422(self, client, snapshots):
        body = prediction_body((snapshots[0], snapshots[0]))

        assert post_prediction(client, body).status_code == 422

    @pytest.mark.parametrize("missing", ["team1_snapshot_id", "team2_snapshot_id", "team1_odds", "best_of"])
    def test_missing_field_returns_422(self, client, snapshots, missing):
        body = prediction_body(snapshots)
        del body[missing]

        assert post_prediction(client, body).status_code == 422

    def test_database_error_returns_500(self, client, snapshots):
        with patch("backend.dota_bet_analyzer.create_prediction", side_effect=sqlite3.OperationalError("locked")):
            response = client.post("/api/predictions", json=prediction_body(snapshots))

        assert response.status_code == 500
        assert response.get_json()["code"] == "FAILED_TO_STORE_PREDICTION"


class TestSnapshotLock:
    """A snapshot used by a prediction is no longer refreshed."""

    def test_used_snapshot_is_not_refreshed(self, client, snapshots):
        post_prediction(client, prediction_body(snapshots))

        response = post_snapshot(client, snapshot_body(101, rating=1700.0), now=DAY1 + 3600)

        assert response.status_code == 200
        assert response.get_json()["snapshot_id"] == snapshots[0]
        assert response.get_json()["taken_at"] == DAY1
        stored = client.get(f"/api/snapshots/{snapshots[0]}").get_json()
        assert stored["data"]["team"]["rating"] == 1500.0

    def test_unused_snapshot_is_still_refreshed(self, client, snapshots):
        post_prediction(client, prediction_body(snapshots))
        other = post_snapshot(client, snapshot_body(303)).get_json()["snapshot_id"]

        post_snapshot(client, snapshot_body(303, rating=1700.0), now=DAY1 + 3600)

        assert client.get(f"/api/snapshots/{other}").get_json()["data"]["team"]["rating"] == 1700.0

    def test_deleting_the_prediction_unlocks_the_snapshot(self, client, snapshots):
        prediction_id = post_prediction(client, prediction_body(snapshots)).get_json()["prediction_id"]
        client.delete(f"/api/predictions/{prediction_id}")

        post_snapshot(client, snapshot_body(101, rating=1700.0), now=DAY1 + 3600)

        assert client.get(f"/api/snapshots/{snapshots[0]}").get_json()["data"]["team"]["rating"] == 1700.0


class TestListPredictions:
    """GET /api/predictions."""

    @pytest.fixture
    def saved(self, client, snapshots):
        """Two predictions: the older one settled, the newer one pending."""
        first = post_prediction(client, prediction_body(snapshots), now=DAY1 + 600).get_json()["prediction_id"]
        second = post_prediction(client, prediction_body(snapshots), now=DAY1 + 1200).get_json()["prediction_id"]
        client.patch(f"/api/predictions/{first}", json={"team1_maps_won": 2, "team2_maps_won": 1})
        return first, second

    def test_lists_newest_first(self, client, saved):
        response = client.get("/api/predictions")

        assert response.status_code == 200
        predictions = response.get_json()
        assert [p["prediction_id"] for p in predictions] == [saved[1], saved[0]]
        assert predictions[0]["team1"]["name"] == "Team 101"
        assert "team1_snapshot" not in predictions[0]

    @pytest.mark.parametrize(("status", "index"), [("pending", 1), ("settled", 0)])
    def test_filters_by_status(self, client, saved, status, index):
        predictions = client.get(f"/api/predictions?status={status}").get_json()

        assert [p["prediction_id"] for p in predictions] == [saved[index]]

    def test_empty_list(self, client):
        assert client.get("/api/predictions").get_json() == []

    def test_invalid_status_returns_422(self, client):
        assert client.get("/api/predictions?status=won").status_code == 422

    def test_database_error_returns_500(self, client):
        with patch("backend.dota_bet_analyzer.list_predictions", side_effect=sqlite3.OperationalError("locked")):
            response = client.get("/api/predictions")

        assert response.status_code == 500
        assert response.get_json()["code"] == "FAILED_TO_READ_PREDICTIONS"


class TestGetPrediction:
    """GET /api/predictions/{id}."""

    def test_includes_both_snapshots(self, client, snapshots):
        prediction_id = post_prediction(client, prediction_body(snapshots)).get_json()["prediction_id"]

        response = client.get(f"/api/predictions/{prediction_id}")

        assert response.status_code == 200
        data = response.get_json()
        assert data["team1_snapshot"]["snapshot_id"] == snapshots[0]
        assert data["team2_snapshot"]["snapshot_id"] == snapshots[1]
        assert data["team1_snapshot"]["data"]["team"]["team"] == "Team 101"
        assert data["team2_snapshot"]["data"]["players"] == [{"account_id": 1, "rank": 80, "match_count": 30}]

    def test_unknown_id_returns_404(self, client):
        response = client.get("/api/predictions/12345")

        assert response.status_code == 404
        assert response.get_json()["code"] == "PREDICTION_NOT_FOUND"


class TestReview:
    """PATCH /api/predictions/{id}."""

    def create(self, client, snapshots, **changes):
        """Save a prediction and return its id."""
        return post_prediction(client, prediction_body(snapshots, **changes)).get_json()["prediction_id"]

    @pytest.mark.parametrize(("best_of", "score"), [(1, (1, 0)), (2, (1, 1)), (3, (2, 1)), (3, (0, 2)), (5, (3, 2))])
    def test_valid_result_is_saved(self, client, snapshots, best_of, score):
        prediction_id = self.create(client, snapshots, best_of=best_of)

        response = client.patch(
            f"/api/predictions/{prediction_id}",
            json={"team1_maps_won": score[0], "team2_maps_won": score[1], "review_note": "As expected"},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert (data["team1_maps_won"], data["team2_maps_won"]) == score
        assert data["review_note"] == "As expected"

    @pytest.mark.parametrize(
        ("best_of", "score"),
        [(3, (3, 0)), (3, (2, 2)), (3, (1, 1)), (1, (1, 1)), (2, (2, 1)), (5, (2, 1)), (3, (-1, 2))],
    )
    def test_invalid_result_returns_422(self, client, snapshots, best_of, score):
        prediction_id = self.create(client, snapshots, best_of=best_of)

        response = client.patch(
            f"/api/predictions/{prediction_id}", json={"team1_maps_won": score[0], "team2_maps_won": score[1]}
        )

        assert response.status_code == 422
        assert response.get_json()["code"] == "INVALID_RESULT"
        assert client.get(f"/api/predictions/{prediction_id}").get_json()["team1_maps_won"] is None

    @pytest.mark.parametrize("field", [{"team1_odds": 3.0}, {"comment": "changed"}, {"bet_team": 2}, {"stake": 1}])
    def test_locked_fields_are_rejected(self, client, snapshots, field):
        prediction_id = self.create(client, snapshots)

        response = client.patch(
            f"/api/predictions/{prediction_id}", json={"team1_maps_won": 2, "team2_maps_won": 0, **field}
        )

        assert response.status_code == 422
        stored = client.get(f"/api/predictions/{prediction_id}").get_json()
        assert stored["team1_odds"] == 1.85
        assert stored["comment"] == "Stable core, stand-ins on the other side"

    def test_result_is_required(self, client, snapshots):
        prediction_id = self.create(client, snapshots)

        response = client.patch(f"/api/predictions/{prediction_id}", json={"review_note": "only a note"})

        assert response.status_code == 422

    def test_edit_review_keeps_note_when_omitted(self, client, snapshots):
        prediction_id = self.create(client, snapshots)
        client.patch(
            f"/api/predictions/{prediction_id}", json={"team1_maps_won": 2, "team2_maps_won": 0, "review_note": "n"}
        )

        response = client.patch(f"/api/predictions/{prediction_id}", json={"team1_maps_won": 1, "team2_maps_won": 2})

        data = response.get_json()
        assert (data["team1_maps_won"], data["team2_maps_won"]) == (1, 2)
        assert data["review_note"] == "n"

    @pytest.mark.parametrize(
        ("changes", "score", "bet_won", "profit"),
        [
            ({}, (2, 1), True, 85.0),  # bet on team 1 at 1.85, won
            ({}, (0, 2), False, -100.0),  # lost the stake
            ({"bet_team": 2}, (1, 2), True, 105.0),  # team 2 at 2.05
            ({"bet_team": None, "stake": None}, (2, 0), None, None),  # no bet
            ({"stake": None}, (2, 0), True, None),  # bet without a stake
            ({"best_of": 2}, (1, 1), False, -100.0),  # a bo2 draw loses a series-win bet
        ],
    )
    def test_bet_outcome(self, client, snapshots, changes, score, bet_won, profit):
        prediction_id = self.create(client, snapshots, **changes)

        data = client.patch(
            f"/api/predictions/{prediction_id}", json={"team1_maps_won": score[0], "team2_maps_won": score[1]}
        ).get_json()

        assert data["bet_won"] is bet_won
        assert data["profit"] == profit
        listed = client.get("/api/predictions").get_json()[0]
        assert (listed["bet_won"], listed["profit"]) == (bet_won, profit)

    def test_unknown_id_returns_404(self, client):
        response = client.patch("/api/predictions/12345", json={"team1_maps_won": 2, "team2_maps_won": 0})

        assert response.status_code == 404
        assert response.get_json()["code"] == "PREDICTION_NOT_FOUND"


class TestDeletePrediction:
    """DELETE /api/predictions/{id}."""

    def test_deletes_prediction_and_keeps_snapshots(self, client, snapshots):
        prediction_id = post_prediction(client, prediction_body(snapshots)).get_json()["prediction_id"]

        assert client.delete(f"/api/predictions/{prediction_id}").status_code == 204
        assert client.get(f"/api/predictions/{prediction_id}").status_code == 404
        assert client.delete(f"/api/predictions/{prediction_id}").status_code == 404
        assert client.get(f"/api/snapshots/{snapshots[0]}").status_code == 200


class TestHelpers:
    """Result validation and bet outcome without the API."""

    @pytest.mark.parametrize(
        ("best_of", "valid", "invalid"),
        [
            (1, [(1, 0), (0, 1)], [(0, 0), (1, 1), (2, 0)]),
            (2, [(2, 0), (1, 1), (0, 2)], [(1, 0), (2, 1), (0, 0)]),
            (3, [(2, 0), (2, 1), (1, 2), (0, 2)], [(3, 0), (2, 2), (1, 0), (1, 1)]),
            (5, [(3, 0), (3, 1), (3, 2), (2, 3)], [(3, 3), (4, 1), (2, 2), (2, 0)]),
        ],
    )
    def test_is_valid_result(self, best_of, valid, invalid):
        assert all(is_valid_result(best_of, *score) for score in valid)
        assert not any(is_valid_result(best_of, *score) for score in invalid)

    def test_pending_has_no_outcome(self):
        prediction = {
            "bet_team": 1,
            "stake": 10,
            "team1_odds": 2.0,
            "team2_odds": 2.0,
            "team1_maps_won": None,
            "team2_maps_won": None,
        }

        assert bet_outcome(prediction) == (None, None)


def test_predictions_table_is_in_predictions_db_only(app, client, snapshots):
    """predictions goes to predictions.sqlite, not the d2ba cache."""
    post_prediction(client, prediction_body(snapshots))

    d2ba = sqlite3.connect(f"{app.instance_path}/d2ba.sqlite")
    predictions = sqlite3.connect(f"{app.instance_path}/predictions.sqlite")
    try:
        assert predictions.execute("SELECT COUNT(*) FROM predictions").fetchone()[0] == 1
        assert "predictions" not in {r[0] for r in d2ba.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        d2ba.close()
        predictions.close()

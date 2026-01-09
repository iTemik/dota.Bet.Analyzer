import requests

from backend.stats import StatsResponse, compute_statistics


class DummyResponse:
    def __init__(self, status_code, json_obj):
        self.status_code = status_code
        self._json = json_obj

    def json(self):
        return self._json


def test_compute_statistics_returns_model(monkeypatch):
    # Mock requests.get to return a successful response with expected JSON
    def fake_get(url, timeout=5):
        return DummyResponse(200, {"command": "SELECT", "rows": [{"team_id": 42, "name": "Alpha", "tag": "A"}]})

    monkeypatch.setattr(requests, "get", fake_get)

    res = compute_statistics(["A"])
    assert isinstance(res, StatsResponse)
    assert len(res.teams) == 1
    team = res.teams[0]
    assert team.team == "Alpha"  # team field gets the name from the response
    assert team.team_id == 42
    assert team.tag == "A"
    # assert team.players[0].name == "Alpha_Player1"  # TODO: players list is not implemented yet
    assert len(team.players) == 0
    assert team.error_code is None
    assert team.error_message is None


def test_compute_statistics_invalid_team():
    res = compute_statistics([""])
    assert isinstance(res, StatsResponse)
    assert len(res.teams) == 1
    team = res.teams[0]
    assert team.error_code == "INVALID_TEAM_NAME"
    assert team.error_message == "Invalid team name"
    assert team.team_id is None


def test_compute_statistics_network_error(monkeypatch):
    # Simulate network error
    def fake_get(url, timeout=5):
        raise RuntimeError("connection failed")

    monkeypatch.setattr(requests, "get", fake_get)

    res = compute_statistics(["A"])
    assert isinstance(res, StatsResponse)
    assert len(res.teams) == 1
    team = res.teams[0]
    assert team.team == "A"
    assert team.error_code == "NETWORK_ERROR"
    assert "connection failed" in team.error_message
    assert team.team_id is None


def test_compute_statistics_non_200(monkeypatch):
    def fake_get(url, timeout=5):
        return DummyResponse(500, {})

    monkeypatch.setattr(requests, "get", fake_get)

    res = compute_statistics(["A"])
    assert isinstance(res, StatsResponse)
    assert len(res.teams) == 1
    team = res.teams[0]
    assert team.team == "A"
    assert team.error_code == "HTTP_ERROR"
    assert "500" in team.error_message
    assert team.team_id is None


def test_compute_statistics_malformed_response(monkeypatch):
    # JSON lacks expected rows
    def fake_get(url, timeout=5):
        return DummyResponse(200, {"command": "SELECT", "rows": []})

    monkeypatch.setattr(requests, "get", fake_get)

    res = compute_statistics(["A"])
    assert isinstance(res, StatsResponse)
    assert len(res.teams) == 1
    team = res.teams[0]
    assert team.team == "A"
    assert team.error_code == "RESPONSE_PARSE_ERROR"
    assert "No rows" in team.error_message
    assert team.team_id is None

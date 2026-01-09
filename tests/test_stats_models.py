import requests

from backend.stats import StatisticsError, StatsResponse, compute_statistics


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
    assert team.team == "A"
    assert team.team_id == 42
    assert team.players[0].name == "Alpha_Player1"


def test_compute_statistics_invalid_team():
    try:
        compute_statistics([""])
        AssertionError("Expected ValueError for empty team name")
    except ValueError:
        pass


def test_compute_statistics_network_error(monkeypatch):
    # Simulate network error
    def fake_get(url, timeout=5):
        raise RuntimeError("connection failed")

    monkeypatch.setattr(requests, "get", fake_get)

    try:
        compute_statistics(["A"])
        AssertionError("Expected StatisticsError on network failure")
    except StatisticsError as e:
        assert "Network error" in str(e)


def test_compute_statistics_non_200(monkeypatch):
    def fake_get(url, timeout=5):
        return DummyResponse(500, {})

    monkeypatch.setattr(requests, "get", fake_get)

    try:
        compute_statistics(["A"])
        AssertionError("Expected StatisticsError on non-200 response")
    except StatisticsError:
        pass


def test_compute_statistics_malformed_response(monkeypatch):
    # JSON lacks expected rows
    def fake_get(url, timeout=5):
        return DummyResponse(200, {"command": "SELECT", "rows": []})

    monkeypatch.setattr(requests, "get", fake_get)

    try:
        compute_statistics(["A"])
        AssertionError("Expected StatisticsError on malformed response")
    except StatisticsError as e:
        assert "Malformed explorer response" in str(e) or "No rows" in str(e)

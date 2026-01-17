import requests

from backend.stats import Player, StatsResponse, compute_statistics


class DummyResponse:
    def __init__(self, status_code, json_obj):
        self.status_code = status_code
        self._json = json_obj

    def json(self):
        return self._json


def test_compute_statistics_returns_model(monkeypatch):
    # Mock requests.get to return a successful response with expected JSON
    def fake_get(url, timeout=5):
        return DummyResponse(
            200,
            {
                "command": "SELECT",
                "rows": [{"team_id": 42, "name": "Alpha", "tag": "A", "rating": 2500.5, "delta": -12.3}],
            },
        )

    # Mock the Celery task
    class FakeTask:
        id = "fake-task-id-123"

    class MockPlayersStatisticsTask:
        @staticmethod
        def delay(**kwargs):
            return FakeTask()

    # Mock time.time() to return a fixed value
    def fake_time():
        return 1768287333.0

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(
        "backend.stats.get_players_by_team", lambda team_id: ([Player(name="Alpha_Player1", id=101)], [])
    )
    monkeypatch.setattr(
        "backend.stats._fetch_team_stats", lambda team_id: ({"logo_url": "https://example.com/alpha_logo.png"}, None)
    )
    monkeypatch.setattr("backend.stats.time.time", fake_time)
    # Mock the import inside compute_statistics by patching dota_bet_analyzer module
    import sys
    from unittest.mock import MagicMock

    mock_dota_bet = MagicMock()
    mock_dota_bet.players_statistics_task = MockPlayersStatisticsTask()
    sys.modules["backend.dota_bet_analyzer"] = mock_dota_bet
    monkeypatch.setitem(sys.modules, "backend.dota_bet_analyzer", mock_dota_bet)

    res = compute_statistics(["A"])
    assert isinstance(res, StatsResponse)
    assert len(res.teams) == 1
    team = res.teams[0]
    assert team.team == "Alpha"  # team field gets the name from the response
    assert team.team_id == 42
    assert team.tag == "A"
    assert team.rating == 2500.5
    assert team.delta == -12.3
    assert team.logo_url == "https://example.com/alpha_logo.png"
    assert len(team.players) == 1
    assert team.players[0].name == "Alpha_Player1"
    assert team.players[0].id == 101
    assert team.task_id == "task_1768287333"  # Verify task_id is set with mocked time
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
    assert team.error_message is not None and "connection failed" in team.error_message
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
    assert team.error_message is not None and "500" in team.error_message
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
    assert team.error_message is not None and "No rows" in team.error_message
    assert team.team_id is None

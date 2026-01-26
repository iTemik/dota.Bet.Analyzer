"""Tests for REST API endpoints status codes and response types."""

import json
from unittest.mock import patch

import pytest

from backend import create_app


def raise_connection_error():
    """Helper function to raise ConnectionError for mocking."""
    raise ConnectionError("Failed to connect to OpenDota API")


def raise_value_error():
    """Helper function to raise ValueError for mocking."""
    raise ValueError("Invalid response format")


@pytest.fixture
def app():
    """Create and configure a test Flask application."""
    return create_app(test_config={})


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


class TestVersionEndpoint:
    """Test suite for /version endpoint."""

    def test_version_returns_200_status(self, client):
        """Test that /version returns 200 status code."""
        rv = client.get("/api/version")
        assert rv.status_code == 200, f"Expected 200, got {rv.status_code}"

    def test_version_returns_json_response(self, client):
        """Test that /version returns valid JSON."""
        rv = client.get("/api/version")
        assert rv.status_code == 200
        data = rv.get_json()
        assert isinstance(data, dict)

    def test_version_contains_backend_version(self, client):
        """Test that response contains backend version field."""
        rv = client.get("/api/version")
        assert rv.status_code == 200
        data = rv.get_json()
        assert "backend" in data
        assert isinstance(data["backend"], str)

    def test_version_contains_build_number(self, client):
        """Test that response contains build number field."""
        rv = client.get("/api/version")
        assert rv.status_code == 200
        data = rv.get_json()
        assert "build" in data
        assert isinstance(data["build"], str)


class TestStreamProgressEndpoint:
    """Test suite for /stream-progress/<task_id> endpoint."""

    def test_stream_progress_returns_200_status(self, client):
        """Test that /stream-progress returns 200 status code."""
        with patch("backend.dota_bet_analyzer.redis_client") as mock_redis:
            # Mock Redis to return completed progress immediately
            mock_redis.get.side_effect = [json.dumps({"step": 1, "message": "test", "progress": 100}).encode()]
            rv = client.get("/api/stream-progress/test-task-123")
            assert rv.status_code == 200

    def test_stream_progress_returns_event_stream(self, client):
        """Test that /stream-progress returns correct Content-Type."""
        with patch("backend.dota_bet_analyzer.redis_client") as mock_redis:
            # Return completed task immediately to avoid streaming
            mock_redis.get.side_effect = [json.dumps({"step": 1, "message": "test", "progress": 100}).encode()]
            rv = client.get("/api/stream-progress/test-task-123")
            assert rv.status_code == 200
            assert "text/event-stream" in rv.content_type

    def test_stream_progress_includes_cors_headers(self, client):
        """Test that /stream-progress includes CORS headers."""
        with patch("backend.dota_bet_analyzer.redis_client") as mock_redis:
            # Return completed task immediately
            mock_redis.get.side_effect = [json.dumps({"step": 1, "message": "test", "progress": 100}).encode()]
            rv = client.get("/api/stream-progress/test-task-123")
            assert rv.status_code == 200
            assert "Access-Control-Allow-Origin" in rv.headers


class TestResultsEndpoint:
    """Test suite for /results/<task_id> endpoint."""

    def test_results_returns_200_when_found(self, client):
        """Test that /results returns 200 when results are found."""
        test_data = {"results": [{"account_id": 123, "matches": []}], "successful": 1, "total": 1}
        with patch("backend.dota_bet_analyzer.redis_client") as mock_redis:
            mock_redis.get.return_value = json.dumps(test_data).encode()
            rv = client.get("/api/results/test-task-123")
            assert rv.status_code == 200

    def test_results_returns_404_when_not_found(self, client):
        """Test that /results returns 404 when results not found."""
        with patch("backend.dota_bet_analyzer.redis_client") as mock_redis:
            mock_redis.get.return_value = None
            rv = client.get("/api/results/nonexistent-task")
            assert rv.status_code == 404

    def test_results_returns_json_response(self, client):
        """Test that /results returns valid JSON response."""
        test_data = {"results": [], "successful": 0, "total": 1}
        with patch("backend.dota_bet_analyzer.redis_client") as mock_redis:
            mock_redis.get.return_value = json.dumps(test_data).encode()
            rv = client.get("/api/results/test-task-456")
            assert rv.status_code == 200
            data = rv.get_json()
            assert isinstance(data, dict)
            assert "results" in data

    def test_results_404_response_contains_error(self, client):
        """Test that 404 response contains error message."""
        with patch("backend.dota_bet_analyzer.redis_client") as mock_redis:
            mock_redis.get.return_value = None
            rv = client.get("/api/results/nonexistent")
            assert rv.status_code == 404
            data = rv.get_json()
            assert "code" in data
            assert "message" in data


class TestStatisticsEndpoint:
    """Test suite for /statistics endpoint status codes."""

    def test_statistics_get_returns_200_on_success(self, monkeypatch):
        """Test that GET /statistics returns 200 on success."""
        from backend.stats import Player, StatsResponse, TeamStats

        def fake_compute(teams):
            return StatsResponse(
                teams=[
                    TeamStats(team=team, team_id=idx + 1, players=[Player(name=f"{team}Player", id=idx + 1)])
                    for idx, team in enumerate(teams)
                ]
            )

        monkeypatch.setattr("backend.dota_bet_analyzer.compute_statistics", fake_compute)

        app = create_app(test_config={})
        client = app.test_client()

        rv = client.get("/api/statistics?team=TestTeam")
        assert rv.status_code == 200, f"Expected 200, got {rv.status_code}"

    def test_statistics_get_returns_422_when_no_teams(self):
        """Test that GET /statistics returns 422 when no teams provided."""
        app = create_app(test_config={})
        client = app.test_client()

        rv = client.get("/api/statistics")
        assert rv.status_code == 422, f"Expected 422, got {rv.status_code}"
        data = rv.get_json()
        assert "code" in data
        assert data["code"] == "MISSING_TEAMS"
        assert "message" in data

    def test_statistics_returns_422_when_too_many_teams(self, monkeypatch):
        """Test that /statistics returns 422 when more than 10 teams (schema validation)."""
        from backend.stats import StatsResponse

        def fake_compute(teams):
            return StatsResponse(teams=[])

        monkeypatch.setattr("backend.dota_bet_analyzer.compute_statistics", fake_compute)

        app = create_app(test_config={})
        client = app.test_client()

        teams_query = "&".join([f"team=Team{i}" for i in range(11)])
        rv = client.get(f"/api/statistics?{teams_query}")
        # flask-smorest returns 422 for schema validation errors
        assert rv.status_code == 422, f"Expected 422, got {rv.status_code}"
        data = rv.get_json()
        # Schema validation returns flask-smorest standard error format
        assert data["code"] == 422
        assert "errors" in data or "message" in data  # flask-smorest error structure

    def test_statistics_unsupported_method_returns_405(self):
        """Test that unsupported HTTP methods return 405 Method Not Allowed."""
        app = create_app(test_config={})
        client = app.test_client()

        rv = client.post("/api/statistics", json={"teams": ["Team1"]})
        assert rv.status_code == 405

        rv = client.put("/api/statistics", json={"teams": ["Team1"]})
        assert rv.status_code == 405


class TestProPlayersEndpoint:
    """Test suite for /pro-players/sync endpoint."""

    def test_pro_players_returns_200_on_success(self, monkeypatch):
        """Test that /pro-players/sync returns 200 on success."""
        monkeypatch.setattr("backend.dota_bet_analyzer.fetch_pro_players_from_api", lambda: [])
        monkeypatch.setattr("backend.dota_bet_analyzer.store_pro_players", lambda x: 0)

        app = create_app(test_config={})
        client = app.test_client()

        rv = client.post("/api/pro-players/sync")
        assert rv.status_code == 200, f"Expected 200, got {rv.status_code}"

    def test_pro_players_returns_503_on_connection_error(self, monkeypatch):
        """Test that /pro-players/sync returns 503 when connection error occurs."""
        monkeypatch.setattr("backend.dota_bet_analyzer.fetch_pro_players_from_api", raise_connection_error)

        app = create_app(test_config={})
        client = app.test_client()

        rv = client.post("/api/pro-players/sync")
        assert rv.status_code == 503, f"Expected 503, got {rv.status_code}"
        data = rv.get_json()
        assert "code" in data

    def test_pro_players_returns_502_on_invalid_response(self, monkeypatch):
        """Test that /pro-players/sync returns 502 when API response is invalid."""
        monkeypatch.setattr("backend.dota_bet_analyzer.fetch_pro_players_from_api", raise_value_error)

        app = create_app(test_config={})
        client = app.test_client()

        rv = client.post("/api/pro-players/sync")
        assert rv.status_code == 502, f"Expected 502, got {rv.status_code}"
        data = rv.get_json()
        assert "code" in data

    def test_pro_players_returns_json_response(self, monkeypatch):
        """Test that /pro-players/sync returns valid JSON."""
        monkeypatch.setattr("backend.dota_bet_analyzer.fetch_pro_players_from_api", lambda: [])
        monkeypatch.setattr("backend.dota_bet_analyzer.store_pro_players", lambda x: 5)

        app = create_app(test_config={})
        client = app.test_client()

        rv = client.post("/api/pro-players/sync")
        assert rv.status_code == 200
        data = rv.get_json()
        assert isinstance(data, dict)
        assert "message" in data or "error_code" in data


class TestTeamsEndpoint:
    """Test suite for /teams/sync endpoint."""

    def test_teams_returns_200_on_success(self, monkeypatch):
        """Test that /teams/sync returns 200 on success."""
        monkeypatch.setattr("backend.dota_bet_analyzer.fetch_teams_from_api", lambda: [])
        monkeypatch.setattr("backend.dota_bet_analyzer.store_teams", lambda x: 0)

        app = create_app(test_config={})
        client = app.test_client()

        rv = client.post("/api/teams/sync")
        assert rv.status_code == 200, f"Expected 200, got {rv.status_code}"

    def test_teams_returns_503_on_connection_error(self, monkeypatch):
        """Test that /teams/sync returns 503 when connection error occurs."""
        monkeypatch.setattr("backend.dota_bet_analyzer.fetch_teams_from_api", raise_connection_error)

        app = create_app(test_config={})
        client = app.test_client()

        rv = client.post("/api/teams/sync")
        assert rv.status_code == 503, f"Expected 503, got {rv.status_code}"
        data = rv.get_json()
        assert "code" in data

    def test_teams_returns_502_on_invalid_response(self, monkeypatch):
        """Test that /teams/sync returns 502 when API response is invalid."""
        monkeypatch.setattr("backend.dota_bet_analyzer.fetch_teams_from_api", raise_value_error)

        app = create_app(test_config={})
        client = app.test_client()

        rv = client.post("/api/teams/sync")
        assert rv.status_code == 502, f"Expected 502, got {rv.status_code}"
        data = rv.get_json()
        assert "code" in data

    def test_teams_returns_json_response(self, monkeypatch):
        """Test that /teams/sync returns valid JSON."""
        monkeypatch.setattr("backend.dota_bet_analyzer.fetch_teams_from_api", lambda: [])
        monkeypatch.setattr("backend.dota_bet_analyzer.store_teams", lambda x: 5)

        app = create_app(test_config={})
        client = app.test_client()

        rv = client.post("/api/teams/sync")
        assert rv.status_code == 200
        data = rv.get_json()
        assert isinstance(data, dict)
        assert "message" in data or "error_code" in data

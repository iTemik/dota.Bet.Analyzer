"""Tests for REST API endpoints status codes and response types."""

import json
from unittest.mock import patch

import pytest

from backend import create_app


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
        rv = client.get("/version")
        assert rv.status_code == 200, f"Expected 200, got {rv.status_code}"

    def test_version_returns_json_response(self, client):
        """Test that /version returns valid JSON."""
        rv = client.get("/version")
        assert rv.status_code == 200
        data = rv.get_json()
        assert isinstance(data, dict)

    def test_version_contains_backend_version(self, client):
        """Test that response contains backend version field."""
        rv = client.get("/version")
        assert rv.status_code == 200
        data = rv.get_json()
        assert "backend" in data
        assert isinstance(data["backend"], str)

    def test_version_contains_build_number(self, client):
        """Test that response contains build number field."""
        rv = client.get("/version")
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
            rv = client.get("/stream-progress/test-task-123")
            assert rv.status_code == 200

    def test_stream_progress_returns_event_stream(self, client):
        """Test that /stream-progress returns correct Content-Type."""
        with patch("backend.dota_bet_analyzer.redis_client") as mock_redis:
            # Return completed task immediately to avoid streaming
            mock_redis.get.side_effect = [json.dumps({"step": 1, "message": "test", "progress": 100}).encode()]
            rv = client.get("/stream-progress/test-task-123")
            assert rv.status_code == 200
            assert "text/event-stream" in rv.content_type

    def test_stream_progress_includes_cors_headers(self, client):
        """Test that /stream-progress includes CORS headers."""
        with patch("backend.dota_bet_analyzer.redis_client") as mock_redis:
            # Return completed task immediately
            mock_redis.get.side_effect = [json.dumps({"step": 1, "message": "test", "progress": 100}).encode()]
            rv = client.get("/stream-progress/test-task-123")
            assert rv.status_code == 200
            assert "Access-Control-Allow-Origin" in rv.headers


class TestResultsEndpoint:
    """Test suite for /results/<task_id> endpoint."""

    def test_results_returns_200_when_found(self, client):
        """Test that /results returns 200 when results are found."""
        test_data = {"results": [{"account_id": 123, "matches": []}], "successful": 1, "total": 1}
        with patch("backend.dota_bet_analyzer.redis_client") as mock_redis:
            mock_redis.get.return_value = json.dumps(test_data).encode()
            rv = client.get("/results/test-task-123")
            assert rv.status_code == 200

    def test_results_returns_404_when_not_found(self, client):
        """Test that /results returns 404 when results not found."""
        with patch("backend.dota_bet_analyzer.redis_client") as mock_redis:
            mock_redis.get.return_value = None
            rv = client.get("/results/nonexistent-task")
            assert rv.status_code == 404

    def test_results_returns_json_response(self, client):
        """Test that /results returns valid JSON response."""
        test_data = {"results": [], "successful": 0, "total": 1}
        with patch("backend.dota_bet_analyzer.redis_client") as mock_redis:
            mock_redis.get.return_value = json.dumps(test_data).encode()
            rv = client.get("/results/test-task-456")
            assert rv.status_code == 200
            data = rv.get_json()
            assert isinstance(data, dict)
            assert "results" in data

    def test_results_404_response_contains_error(self, client):
        """Test that 404 response contains error message."""
        with patch("backend.dota_bet_analyzer.redis_client") as mock_redis:
            mock_redis.get.return_value = None
            rv = client.get("/results/nonexistent")
            assert rv.status_code == 404
            data = rv.get_json()
            assert "error" in data


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

        rv = client.get("/statistics?team=TestTeam")
        assert rv.status_code == 200, f"Expected 200, got {rv.status_code}"

    def test_statistics_post_returns_200_on_success(self, monkeypatch):
        """Test that POST /statistics returns 200 on success."""
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

        rv = client.post("/statistics", json={"teams": ["Team1"]})
        assert rv.status_code == 200, f"Expected 200, got {rv.status_code}"

    def test_statistics_get_returns_400_when_no_teams(self):
        """Test that GET /statistics returns 400 when no teams provided."""
        app = create_app(test_config={})
        client = app.test_client()

        rv = client.get("/statistics")
        assert rv.status_code == 400, f"Expected 400, got {rv.status_code}"
        data = rv.get_json()
        assert "error" in data

    def test_statistics_post_returns_400_when_no_teams(self):
        """Test that POST /statistics returns 400 when no teams provided."""
        app = create_app(test_config={})
        client = app.test_client()

        rv = client.post("/statistics", json={})
        assert rv.status_code == 400, f"Expected 400, got {rv.status_code}"
        data = rv.get_json()
        assert "error" in data

    def test_statistics_returns_400_when_too_many_teams(self, monkeypatch):
        """Test that /statistics returns 400 when more than 10 teams."""
        from backend.stats import StatsResponse

        def fake_compute(teams):
            return StatsResponse(teams=[])

        monkeypatch.setattr("backend.dota_bet_analyzer.compute_statistics", fake_compute)

        app = create_app(test_config={})
        client = app.test_client()

        teams = [f"Team{i}" for i in range(11)]
        rv = client.post("/statistics", json={"teams": teams})
        assert rv.status_code == 400, f"Expected 400, got {rv.status_code}"

    def test_statistics_unsupported_method_returns_405(self):
        """Test that unsupported HTTP method returns 405 Method Not Allowed."""
        app = create_app(test_config={})
        client = app.test_client()

        rv = client.put("/statistics", json={"teams": ["Team1"]})
        assert rv.status_code == 405


class TestProPlayersEndpoint:
    """Test suite for /pro-players/sync endpoint."""

    def test_pro_players_returns_200_on_success(self, monkeypatch):
        """Test that /pro-players/sync returns 200 on success."""
        monkeypatch.setattr("backend.dota_bet_analyzer.fetch_pro_players_from_api", lambda: [])
        monkeypatch.setattr("backend.dota_bet_analyzer.store_pro_players", lambda x: 0)

        app = create_app(test_config={})
        client = app.test_client()

        rv = client.post("/pro-players/sync")
        assert rv.status_code == 200, f"Expected 200, got {rv.status_code}"

    def test_pro_players_returns_500_on_fetch_failure(self, monkeypatch):
        """Test that /pro-players/sync returns 500 when fetch fails."""
        monkeypatch.setattr("backend.dota_bet_analyzer.fetch_pro_players_from_api", lambda: None)

        app = create_app(test_config={})
        client = app.test_client()

        rv = client.post("/pro-players/sync")
        assert rv.status_code == 500, f"Expected 500, got {rv.status_code}"

    def test_pro_players_returns_json_response(self, monkeypatch):
        """Test that /pro-players/sync returns valid JSON."""
        monkeypatch.setattr("backend.dota_bet_analyzer.fetch_pro_players_from_api", lambda: [])
        monkeypatch.setattr("backend.dota_bet_analyzer.store_pro_players", lambda x: 5)

        app = create_app(test_config={})
        client = app.test_client()

        rv = client.post("/pro-players/sync")
        assert rv.status_code == 200
        data = rv.get_json()
        assert isinstance(data, dict)
        assert "status" in data or "error" in data


class TestTeamsEndpoint:
    """Test suite for /teams/sync endpoint."""

    def test_teams_returns_200_on_success(self, monkeypatch):
        """Test that /teams/sync returns 200 on success."""
        monkeypatch.setattr("backend.dota_bet_analyzer.fetch_teams_from_api", lambda: [])
        monkeypatch.setattr("backend.dota_bet_analyzer.store_teams", lambda x: 0)

        app = create_app(test_config={})
        client = app.test_client()

        rv = client.post("/teams/sync")
        assert rv.status_code == 200, f"Expected 200, got {rv.status_code}"

    def test_teams_returns_500_on_fetch_failure(self, monkeypatch):
        """Test that /teams/sync returns 500 when fetch fails."""
        monkeypatch.setattr("backend.dota_bet_analyzer.fetch_teams_from_api", lambda: None)

        app = create_app(test_config={})
        client = app.test_client()

        rv = client.post("/teams/sync")
        assert rv.status_code == 500, f"Expected 500, got {rv.status_code}"

    def test_teams_returns_json_response(self, monkeypatch):
        """Test that /teams/sync returns valid JSON."""
        monkeypatch.setattr("backend.dota_bet_analyzer.fetch_teams_from_api", lambda: [])
        monkeypatch.setattr("backend.dota_bet_analyzer.store_teams", lambda x: 5)

        app = create_app(test_config={})
        client = app.test_client()

        rv = client.post("/teams/sync")
        assert rv.status_code == 200
        data = rv.get_json()
        assert isinstance(data, dict)
        assert "status" in data or "error" in data

"""Tests for /results/<task_id> endpoint."""

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


class TestGetResultsEndpoint:
    """Test suite for /results/<task_id> endpoint."""

    @patch("backend.dota_bet_analyzer.redis_client")
    def test_get_results_returns_200_with_valid_results(self, mock_redis, client):
        """Test that get_results returns 200 with valid results data."""
        # Mock Redis returning valid results
        results_data = {
            "results": [
                {"account_id": 12345, "match_count": 10, "matches": []},
                {"account_id": 67890, "match_count": 15, "matches": []},
            ],
            "successful": 2,
            "total": 2,
            "summary": {"avg_rank": 500, "bad_rank_players": 0},
        }
        mock_redis.get.return_value = json.dumps(results_data).encode()

        rv = client.get("/api/results/task_123")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["successful"] == 2
        assert data["total"] == 2
        assert len(data["results"]) == 2
        assert data["summary"]["avg_rank"] == 500

    @patch("backend.dota_bet_analyzer.redis_client")
    def test_get_results_returns_404_when_not_found(self, mock_redis, client):
        """Test that get_results returns 404 when results don't exist."""
        # Mock Redis returning None (no results found)
        mock_redis.get.return_value = None

        rv = client.get("/api/results/nonexistent_task")

        assert rv.status_code == 404
        data = rv.get_json()
        assert data["status"] == 404
        assert data["code"] == "RESULTS_NOT_FOUND"
        assert "nonexistent_task" in data["details"]["task_id"]

    @patch("backend.dota_bet_analyzer.redis_client")
    def test_get_results_returns_500_on_redis_error(self, mock_redis, client):
        """Test that get_results returns 500 when Redis connection fails."""
        # Mock Redis raising exception
        mock_redis.get.side_effect = ConnectionError("Redis connection failed")

        rv = client.get("/api/results/task_123")

        assert rv.status_code == 500
        data = rv.get_json()
        assert data["status"] == 500
        assert data["code"] == "FAILED_TO_RETRIEVE_RESULTS"
        assert "exception" in data["details"]

    @patch("backend.dota_bet_analyzer.redis_client")
    def test_get_results_returns_500_on_json_decode_error(self, mock_redis, client):
        """Test that get_results returns 500 when Redis contains invalid JSON."""
        # Mock Redis returning invalid JSON
        mock_redis.get.return_value = b"invalid json {{{"

        rv = client.get("/api/results/task_123")

        assert rv.status_code == 500
        data = rv.get_json()
        assert data["status"] == 500
        assert data["code"] == "FAILED_TO_RETRIEVE_RESULTS"

    @patch("backend.dota_bet_analyzer.redis_client")
    def test_get_results_includes_task_id_in_response(self, mock_redis, client):
        """Test that get_results includes task_id in error details."""
        mock_redis.get.return_value = None

        rv = client.get("/api/results/my_custom_task_id")

        assert rv.status_code == 404
        data = rv.get_json()
        assert data["details"]["task_id"] == "my_custom_task_id"

    @patch("backend.dota_bet_analyzer.redis_client")
    def test_get_results_with_empty_results(self, mock_redis, client):
        """Test that get_results handles empty results correctly."""
        # Mock Redis returning empty but valid results
        results_data = {
            "results": [],
            "successful": 0,
            "total": 0,
            "summary": {},
        }
        mock_redis.get.return_value = json.dumps(results_data).encode()

        rv = client.get("/api/results/task_empty")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["successful"] == 0
        assert data["total"] == 0
        assert data["results"] == []

    @patch("backend.dota_bet_analyzer.redis_client")
    def test_get_results_with_partial_failures(self, mock_redis, client):
        """Test that get_results returns results with some failed player fetches."""
        # Mock results with some errors
        results_data = {
            "results": [
                {"account_id": 12345, "match_count": 10, "matches": []},
                {"account_id": 67890, "error": "API rate limit exceeded"},
                {"account_id": 11111, "match_count": 5, "matches": []},
            ],
            "successful": 2,
            "total": 3,
            "summary": {"avg_rank": 600, "bad_rank_players": 1},
        }
        mock_redis.get.return_value = json.dumps(results_data).encode()

        rv = client.get("/api/results/task_partial")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["successful"] == 2
        assert data["total"] == 3
        assert len(data["results"]) == 3
        # Check that error is preserved
        assert "error" in data["results"][1]
        assert data["results"][1]["error"] == "API rate limit exceeded"

    @patch("backend.dota_bet_analyzer.redis_client")
    def test_get_results_preserves_all_summary_fields(self, mock_redis, client):
        """Test that get_results preserves all summary fields from the task."""
        # Mock comprehensive summary data
        results_data = {
            "results": [],
            "successful": 5,
            "total": 5,
            "summary": {
                "avg_rank": 450,
                "bad_rank_players": 2,
                "total_matches": 50,
                "win_rate": 0.55,
                "common_heroes": ["Invoker", "Pudge"],
            },
        }
        mock_redis.get.return_value = json.dumps(results_data).encode()

        rv = client.get("/api/results/task_comprehensive")

        assert rv.status_code == 200
        data = rv.get_json()
        summary = data["summary"]
        assert summary["avg_rank"] == 450
        assert summary["bad_rank_players"] == 2
        assert summary["total_matches"] == 50
        assert summary["win_rate"] == 0.55
        assert "Invoker" in summary["common_heroes"]

    @patch("backend.dota_bet_analyzer.redis_client")
    def test_get_results_different_task_ids(self, mock_redis, client):
        """Test that different task_ids are handled independently."""

        # Setup different results for different task IDs
        def redis_side_effect(key):
            if key == "results:task_1":
                return json.dumps({"results": [], "successful": 1, "total": 1, "summary": {}}).encode()
            elif key == "results:task_2":
                return json.dumps({"results": [], "successful": 2, "total": 2, "summary": {}}).encode()
            else:
                return None

        mock_redis.get.side_effect = redis_side_effect

        # Test task_1
        rv1 = client.get("/api/results/task_1")
        assert rv1.status_code == 200
        data1 = rv1.get_json()
        assert data1["successful"] == 1

        # Test task_2
        rv2 = client.get("/api/results/task_2")
        assert rv2.status_code == 200
        data2 = rv2.get_json()
        assert data2["successful"] == 2

        # Test non-existent
        rv3 = client.get("/api/results/task_3")
        assert rv3.status_code == 404

    @patch("backend.dota_bet_analyzer.redis_client")
    def test_get_results_url_in_error_details(self, mock_redis, client):
        """Test that error responses include the request URL in details."""
        mock_redis.get.return_value = None

        rv = client.get("/api/results/test_task")

        assert rv.status_code == 404
        data = rv.get_json()
        assert "url" in data["details"]
        assert "/api/results/test_task" in data["details"]["url"]

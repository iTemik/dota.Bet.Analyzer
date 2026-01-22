"""Tests for /statistics/players REST API endpoint."""

from unittest.mock import MagicMock, patch

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


class TestPlayersStatisticsEndpoint:
    """Test suite for /statistics/players endpoint."""

    def test_returns_200_status_on_success(self, client):
        """Test that endpoint returns 200 status code on successful request."""
        with patch("backend.dota_bet_analyzer.players_statistics_task") as mock_task:
            mock_task.delay.return_value = MagicMock(id="celery-task-id-123")

            rv = client.get("/api/statistics/players?account_id=123&account_id=456")

            assert rv.status_code == 200
            data = rv.get_json()
            assert data is not None

    def test_returns_task_id_in_response(self, client):
        """Test that response includes task_id and celery_task_id."""
        with patch("backend.dota_bet_analyzer.players_statistics_task") as mock_task:
            mock_task.delay.return_value = MagicMock(id="celery-task-123")

            rv = client.get("/api/statistics/players?account_id=789")

            assert rv.status_code == 200
            data = rv.get_json()
            assert "task_id" in data
            assert "celery_task_id" in data
            assert data["status"] == "started"

    def test_returns_400_when_no_account_ids_provided(self, client):
        """Test that endpoint returns 400 when no account_ids are provided."""
        rv = client.get("/api/statistics/players")

        assert rv.status_code == 400
        data = rv.get_json()
        assert "error_code" in data
        assert "no account_ids provided" in data["message"].lower()

    def test_returns_400_when_too_many_account_ids(self, client):
        """Test that endpoint returns 400 when more than 10 account_ids provided."""
        account_ids = "&".join([f"account_id={i}" for i in range(11)])
        rv = client.get(f"/api/statistics/players?{account_ids}")

        assert rv.status_code == 400
        data = rv.get_json()
        assert "error_code" in data
        assert "max 10" in data["message"].lower() or "too many" in data["message"].lower()

    def test_returns_400_on_invalid_account_id(self, client):
        """Test that endpoint returns 400 when account_id is not a valid integer."""
        rv = client.get("/api/statistics/players?account_id=abc&account_id=123")

        assert rv.status_code == 400
        data = rv.get_json()
        assert "error_code" in data
        assert "invalid account_id" in data["message"].lower()

    def test_returns_400_when_no_valid_account_ids(self, client):
        """Test that endpoint returns 400 when all account_ids are invalid."""
        rv = client.get("/api/statistics/players?account_id=abc&account_id=xyz")

        assert rv.status_code == 400
        data = rv.get_json()
        assert "error_code" in data
        assert "invalid account_id" in data["message"].lower()

    def test_converts_string_account_ids_to_integers(self, client):
        """Test that string account_ids are converted to integers."""
        with patch("backend.dota_bet_analyzer.players_statistics_task") as mock_task:
            mock_task.delay.return_value = MagicMock(id="celery-task-456")

            rv = client.get("/api/statistics/players?account_id=123&account_id=456&account_id=789")

            assert rv.status_code == 200
            # Verify that the task was called with integer account IDs
            mock_task.delay.assert_called_once()
            call_args = mock_task.delay.call_args
            accounts = call_args[1]["accounts"]  # Get 'accounts' kwarg
            assert accounts == [123, 456, 789]
            assert all(isinstance(acc, int) for acc in accounts)

    def test_accepts_days_parameter(self, client):
        """Test that 'days' parameter is accepted and passed to task."""
        with patch("backend.dota_bet_analyzer.players_statistics_task") as mock_task:
            mock_task.delay.return_value = MagicMock(id="celery-task-789")

            rv = client.get("/api/statistics/players?account_id=123&days=30")

            assert rv.status_code == 200
            mock_task.delay.assert_called_once()
            call_args = mock_task.delay.call_args
            assert call_args[1]["days"] == 30

    def test_days_parameter_defaults_to_20(self, client):
        """Test that days parameter defaults to 20 when not provided."""
        with patch("backend.dota_bet_analyzer.players_statistics_task") as mock_task:
            mock_task.delay.return_value = MagicMock(id="celery-task-000")

            rv = client.get("/api/statistics/players?account_id=123")

            assert rv.status_code == 200
            mock_task.delay.assert_called_once()
            call_args = mock_task.delay.call_args
            assert call_args[1]["days"] == 20

    def test_returns_500_on_task_start_failure(self, client):
        """Test that endpoint returns 500 when task fails to start."""
        with patch("backend.dota_bet_analyzer.players_statistics_task") as mock_task:
            mock_task.delay.side_effect = Exception("Celery connection failed")

            rv = client.get("/api/statistics/players?account_id=123")

            assert rv.status_code == 500
            data = rv.get_json()
            assert "error_code" in data
            assert "Failed to start task" in data["message"]

    def test_handles_whitespace_in_account_ids(self, client):
        """Test that whitespace in account_ids is properly trimmed."""
        with patch("backend.dota_bet_analyzer.players_statistics_task") as mock_task:
            mock_task.delay.return_value = MagicMock(id="celery-task-111")

            # Test with spaces around account IDs
            rv = client.get("/api/statistics/players?account_id=%20123%20&account_id=%20456%20")

            assert rv.status_code == 200
            mock_task.delay.assert_called_once()
            call_args = mock_task.delay.call_args
            accounts = call_args[1]["accounts"]
            assert accounts == [123, 456]

    def test_response_json_contains_required_fields(self, client):
        """Test that successful response JSON contains all required fields."""
        with patch("backend.dota_bet_analyzer.players_statistics_task") as mock_task:
            mock_task.delay.return_value = MagicMock(id="celery-task-222")

            rv = client.get("/api/statistics/players?account_id=123&account_id=456")

            assert rv.status_code == 200
            data = rv.get_json()
            assert "status" in data
            assert "task_id" in data
            assert "celery_task_id" in data
            assert data["status"] == "started"
            assert isinstance(data["task_id"], str)
            assert isinstance(data["celery_task_id"], str)


class TestPlayersStatisticsIntegration:
    """Integration tests for /statistics/players endpoint."""

    def test_multiple_valid_account_ids_at_boundary(self, client):
        """Test with exactly 10 account_ids (boundary case)."""
        with patch("backend.dota_bet_analyzer.players_statistics_task") as mock_task:
            mock_task.delay.return_value = MagicMock(id="celery-boundary")

            account_ids = "&".join([f"account_id={i}" for i in range(1, 11)])
            rv = client.get(f"/api/statistics/players?{account_ids}")

            assert rv.status_code == 200
            mock_task.delay.assert_called_once()

    def test_request_with_mixed_valid_and_invalid_ids(self, client):
        """Test that one invalid ID causes entire request to fail."""
        rv = client.get("/api/statistics/players?account_id=123&account_id=invalid&account_id=456")

        assert rv.status_code == 400
        data = rv.get_json()
        assert "error_code" in data

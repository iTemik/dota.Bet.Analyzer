"""Tests for /stream-progress endpoint."""

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


class TestStreamProgressEndpoint:
    """Test suite for /stream-progress/<task_id> endpoint."""

    @patch("backend.dota_bet_analyzer.redis_client")
    def test_stream_progress_task_not_found_returns_404(self, mock_redis, client):
        """Test that stream_progress returns 404 when task doesn't exist."""
        # Mock Redis returning None for non-existent task
        mock_redis.get.return_value = None

        rv = client.get("/api/stream-progress/nonexistent_task")

        assert rv.status_code == 404
        data = rv.get_json()
        assert data["status"] == 404
        assert data["code"] == "RESULTS_NOT_FOUND"
        assert "nonexistent_task" in data["details"]["task_id"]

    @patch("backend.dota_bet_analyzer.redis_client")
    def test_stream_progress_redis_error_returns_500(self, mock_redis, client):
        """Test that stream_progress returns 500 when Redis connection fails."""
        # Mock Redis raising exception on initial check
        mock_redis.get.side_effect = ConnectionError("Redis connection failed")

        rv = client.get("/api/stream-progress/task_123")

        assert rv.status_code == 500
        data = rv.get_json()
        assert data["status"] == 500
        assert data["code"] == "FAILED_TO_RETRIEVE_RESULTS"

    @patch("backend.dota_bet_analyzer.redis_client")
    def test_stream_progress_returns_200_with_sse_headers(self, mock_redis, client):
        """Test that stream_progress returns 200 with proper SSE headers."""
        # Mock initial task exists
        initial_progress = json.dumps({"step": 0, "message": "Starting", "progress": 0, "data": {}})
        mock_redis.get.return_value = initial_progress.encode()

        rv = client.get("/api/stream-progress/task_123")

        assert rv.status_code == 200
        assert rv.content_type.startswith("text/event-stream")
        assert rv.headers.get("Cache-Control") == "no-cache"
        assert rv.headers.get("Connection") == "keep-alive"

    @patch("backend.dota_bet_analyzer.redis_client")
    @patch("backend.dota_bet_analyzer.time.sleep")
    def test_stream_progress_completes_on_100_percent(self, mock_sleep, mock_redis, client):
        """Test that stream completes when progress reaches 100%."""
        # Setup progress sequence: 0% -> 50% -> 100%
        progress_sequence = [
            json.dumps({"step": 0, "message": "Starting", "progress": 0, "data": {}}).encode(),
            json.dumps({"step": 1, "message": "Processing", "progress": 50, "data": {}}).encode(),
            json.dumps({"step": 2, "message": "Complete", "progress": 100, "data": {}}).encode(),
        ]

        mock_redis.get.side_effect = progress_sequence
        mock_sleep.return_value = None  # Skip actual sleep

        rv = client.get("/api/stream-progress/task_123")

        assert rv.status_code == 200
        # Parse SSE stream
        stream_data = rv.data.decode("utf-8")
        lines = [line for line in stream_data.split("\n") if line.strip()]

        # Should have 3 progress updates
        assert len(lines) >= 2  # At least step 1 and step 2 (step 0 might not be sent if not > last_step)

        # Last update should be 100%
        last_update = json.loads(lines[-1])
        assert last_update["progress"] == 100
        assert last_update["step"] == 2

    @patch("backend.dota_bet_analyzer.redis_client")
    @patch("backend.dota_bet_analyzer.time.sleep")
    def test_stream_progress_completes_on_error_state(self, mock_sleep, mock_redis, client):
        """Test that stream completes when progress is -1 (error state)."""
        # Setup progress sequence: 0% -> error (-1)
        progress_sequence = [
            json.dumps({"step": 0, "message": "Starting", "progress": 0, "data": {}}).encode(),
            json.dumps({"step": 1, "message": "Error occurred", "progress": -1, "data": {"error": True}}).encode(),
        ]

        mock_redis.get.side_effect = progress_sequence
        mock_sleep.return_value = None

        rv = client.get("/api/stream-progress/task_123")

        assert rv.status_code == 200
        stream_data = rv.data.decode("utf-8")
        lines = [line for line in stream_data.split("\n") if line.strip()]

        # Last update should be error state
        last_update = json.loads(lines[-1])
        assert last_update["progress"] == -1
        assert last_update["step"] == 1

    @patch("backend.dota_bet_analyzer.redis_client")
    @patch("backend.dota_bet_analyzer.time.sleep")
    def test_stream_progress_timeout_on_no_updates(self, mock_sleep, mock_redis, client):
        """Test that stream times out when no progress updates occur."""
        # Initial check passes
        initial_progress = json.dumps({"step": 0, "message": "Starting", "progress": 0, "data": {}})

        # After initial check, Redis keeps returning same step (no progress)
        # This simulates a stuck task
        mock_redis.get.return_value = initial_progress.encode()
        mock_sleep.return_value = None

        rv = client.get("/api/stream-progress/task_123")

        assert rv.status_code == 200
        stream_data = rv.data.decode("utf-8")
        lines = [line for line in stream_data.split("\n") if line.strip()]

        # Should have timeout error message
        assert len(lines) > 0
        last_update = json.loads(lines[-1])
        assert last_update["progress"] == -1
        assert "timed out" in last_update["message"].lower()
        assert last_update["data"]["timeout"] is True

    @patch("backend.dota_bet_analyzer.redis_client")
    @patch("backend.dota_bet_analyzer.time.sleep")
    @patch("backend.dota_bet_analyzer.time.time")
    def test_stream_progress_timeout_on_max_runtime(self, mock_time, mock_sleep, mock_redis, client):
        """Test that stream times out when max runtime is exceeded."""
        # Initial check passes
        initial_progress = json.dumps({"step": 0, "message": "Starting", "progress": 0, "data": {}}).encode()
        mock_redis.get.return_value = initial_progress

        # Simulate time passing beyond max_runtime (120 seconds)
        start_time = 1000.0
        mock_time.side_effect = [
            start_time,  # start_time assignment
            start_time + 121,  # First check exceeds 120s limit
        ]
        mock_sleep.return_value = None

        rv = client.get("/api/stream-progress/task_123")

        assert rv.status_code == 200
        stream_data = rv.data.decode("utf-8")
        lines = [line for line in stream_data.split("\n") if line.strip()]

        # Should have runtime timeout error
        last_update = json.loads(lines[-1])
        assert last_update["progress"] == -1
        assert "maximum runtime" in last_update["message"].lower()
        assert last_update["data"]["timeout"] is True

    @patch("backend.dota_bet_analyzer.redis_client")
    @patch("backend.dota_bet_analyzer.time.sleep")
    def test_stream_progress_timeout_on_max_iterations(self, mock_sleep, mock_redis, client):
        """Test that stream times out when max iterations is reached."""
        # Initial check passes
        initial_progress = json.dumps({"step": 0, "message": "Starting", "progress": 0, "data": {}}).encode()

        # Create a side effect that:
        # 1. Returns initial progress for the pre-flight check
        # 2. Returns progressing steps but never reaches 100%
        call_count = [0]

        def redis_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Pre-flight check
                return initial_progress
            else:
                # Keep returning increasing steps but never complete
                step = min(call_count[0] - 1, 5999)  # Cap at max_iterations - 1
                return json.dumps({"step": step, "message": f"Step {step}", "progress": 50, "data": {}}).encode()

        mock_redis.get.side_effect = redis_side_effect
        mock_sleep.return_value = None

        rv = client.get("/api/stream-progress/task_123")

        assert rv.status_code == 200
        stream_data = rv.data.decode("utf-8")
        lines = [line for line in stream_data.split("\n") if line.strip()]

        # Should have max iterations error
        last_update = json.loads(lines[-1])
        assert last_update["progress"] == -1
        assert "maximum iterations" in last_update["message"].lower()
        assert last_update["data"]["timeout"] is True

    @patch("backend.dota_bet_analyzer.redis_client")
    @patch("backend.dota_bet_analyzer.time.sleep")
    def test_stream_progress_handles_json_decode_error(self, mock_sleep, mock_redis, client):
        """Test that stream handles invalid JSON gracefully."""
        # Initial check passes with valid JSON
        initial_progress = json.dumps({"step": 0, "message": "Starting", "progress": 0, "data": {}}).encode()

        # After initial check, Redis returns invalid JSON
        mock_redis.get.side_effect = [
            initial_progress,  # Pre-flight check
            b"invalid json {{{",  # Invalid JSON in stream
        ]
        mock_sleep.return_value = None

        rv = client.get("/api/stream-progress/task_123")

        assert rv.status_code == 200
        stream_data = rv.data.decode("utf-8")
        lines = [line for line in stream_data.split("\n") if line.strip()]

        # Should have JSON decode error
        last_update = json.loads(lines[-1])
        assert last_update["progress"] == -1
        assert "invalid progress data" in last_update["message"].lower()
        assert last_update["data"]["error"] is True

    @patch("backend.dota_bet_analyzer.redis_client")
    @patch("backend.dota_bet_analyzer.time.sleep")
    def test_stream_progress_handles_stream_exception(self, mock_sleep, mock_redis, client):
        """Test that stream handles unexpected exceptions gracefully."""
        # Initial check passes
        initial_progress = json.dumps({"step": 0, "message": "Starting", "progress": 0, "data": {}}).encode()

        # After initial check, Redis raises unexpected exception
        mock_redis.get.side_effect = [
            initial_progress,  # Pre-flight check
            RuntimeError("Unexpected error"),  # Unexpected exception in stream
        ]
        mock_sleep.return_value = None

        rv = client.get("/api/stream-progress/task_123")

        assert rv.status_code == 200
        stream_data = rv.data.decode("utf-8")
        lines = [line for line in stream_data.split("\n") if line.strip()]

        # Should have stream error
        last_update = json.loads(lines[-1])
        assert last_update["progress"] == -1
        assert "stream error" in last_update["message"].lower()
        assert last_update["data"]["error"] is True

    @patch("backend.dota_bet_analyzer.redis_client")
    @patch("backend.dota_bet_analyzer.time.sleep")
    def test_stream_progress_only_sends_new_updates(self, mock_sleep, mock_redis, client):
        """Test that stream only sends updates when step increases."""
        # Setup: Same step returned multiple times, then new step
        progress_sequence = [
            json.dumps({"step": 0, "message": "Starting", "progress": 0, "data": {}}).encode(),  # Pre-flight
            json.dumps({"step": 1, "message": "Step 1", "progress": 25, "data": {}}).encode(),  # First new
            json.dumps({"step": 1, "message": "Step 1", "progress": 25, "data": {}}).encode(),  # Duplicate
            json.dumps({"step": 1, "message": "Step 1", "progress": 25, "data": {}}).encode(),  # Duplicate
            json.dumps({"step": 2, "message": "Step 2", "progress": 50, "data": {}}).encode(),  # Second new
            json.dumps({"step": 2, "message": "Step 2", "progress": 50, "data": {}}).encode(),  # Duplicate
            json.dumps({"step": 3, "message": "Complete", "progress": 100, "data": {}}).encode(),  # Complete
        ]

        mock_redis.get.side_effect = progress_sequence
        mock_sleep.return_value = None

        rv = client.get("/api/stream-progress/task_123")

        assert rv.status_code == 200
        stream_data = rv.data.decode("utf-8")
        lines = [line for line in stream_data.split("\n") if line.strip()]

        # Should only have 3 updates (steps 1, 2, 3) - duplicates not sent
        assert len(lines) == 3

        # Verify steps are in order
        updates = [json.loads(line) for line in lines]
        assert updates[0]["step"] == 1
        assert updates[1]["step"] == 2
        assert updates[2]["step"] == 3
        assert updates[2]["progress"] == 100

    @patch("backend.dota_bet_analyzer.redis_client")
    @patch("backend.dota_bet_analyzer.time.sleep")
    def test_stream_progress_with_task_data(self, mock_sleep, mock_redis, client):
        """Test that stream includes data payloads from Redis."""
        # Setup progress with data payloads
        progress_sequence = [
            json.dumps({"step": 0, "message": "Starting", "progress": 0, "data": {}}).encode(),
            json.dumps(
                {
                    "step": 1,
                    "message": "Fetched matches",
                    "progress": 50,
                    "data": {"account_id": 12345, "match_count": 10},
                }
            ).encode(),
            json.dumps(
                {
                    "step": 2,
                    "message": "Complete",
                    "progress": 100,
                    "data": {"successful": 1, "total": 1},
                }
            ).encode(),
        ]

        mock_redis.get.side_effect = progress_sequence
        mock_sleep.return_value = None

        rv = client.get("/api/stream-progress/task_123")

        assert rv.status_code == 200
        stream_data = rv.data.decode("utf-8")
        lines = [line for line in stream_data.split("\n") if line.strip()]

        # Verify data is included
        update_1 = json.loads(lines[0])
        assert update_1["data"]["account_id"] == 12345
        assert update_1["data"]["match_count"] == 10

        update_2 = json.loads(lines[1])
        assert update_2["data"]["successful"] == 1
        assert update_2["data"]["total"] == 1

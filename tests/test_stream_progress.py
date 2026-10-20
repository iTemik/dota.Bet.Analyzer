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


def snapshot(step: int, progress: float, message: str = "Working", data: dict | None = None) -> bytes:
    """Build a stored progress snapshot as update_progress writes it."""
    return json.dumps({"step": step, "message": message, "progress": progress, "data": data or {}}).encode()


class FakeProgress:
    """Stand-in for Redis and the clock: each wait for a progress signal moves to the next snapshot.

    The last snapshot stays stored once the list runs out. Each wait advances the clock by
    `wait_seconds`, as a blocking wait without a signal would.
    """

    def __init__(self, mock_redis, mock_monotonic, snapshots: list, wait_seconds: float = 0.1) -> None:
        self.snapshots = snapshots
        self.index = 0
        self.now = 1000.0
        self.wait_seconds = wait_seconds
        self.subscription = mock_redis.pubsub.return_value
        mock_redis.get.side_effect = self.get
        self.subscription.get_message.side_effect = self.wait
        mock_monotonic.side_effect = lambda: self.now

    def get(self, key: str):
        value = self.snapshots[min(self.index, len(self.snapshots) - 1)]
        if isinstance(value, Exception):
            raise value
        return value

    def wait(self, timeout: float):
        self.index += 1
        self.now += self.wait_seconds
        return None


@pytest.fixture
def fake_progress():
    """Patch Redis and the stream clock; call the result with the snapshots to serve."""
    with (
        patch("backend.task_store.redis_client") as mock_redis,
        patch("backend.dota_bet_analyzer.time.monotonic") as mock_monotonic,
    ):
        yield lambda snapshots, **kwargs: FakeProgress(mock_redis, mock_monotonic, snapshots, **kwargs)


def stream_lines(rv) -> list[dict]:
    """Decode the NDJSON stream body."""
    return [json.loads(line) for line in rv.data.decode("utf-8").split("\n") if line.strip()]


class TestStreamProgressEndpoint:
    """Test suite for /stream-progress/<task_id> endpoint."""

    @patch("backend.task_store.redis_client")
    def test_stream_progress_task_not_found_returns_404(self, mock_redis, client):
        """Test that stream_progress returns 404 when task doesn't exist."""
        mock_redis.get.return_value = None

        rv = client.get("/api/stream-progress/nonexistent_task")

        assert rv.status_code == 404
        data = rv.get_json()
        assert data["status"] == 404
        assert data["code"] == "RESULTS_NOT_FOUND"
        assert "nonexistent_task" in data["details"]["task_id"]

    @patch("backend.task_store.redis_client")
    def test_stream_progress_redis_error_returns_500(self, mock_redis, client):
        """Test that stream_progress returns 500 when Redis connection fails."""
        mock_redis.get.side_effect = ConnectionError("Redis connection failed")

        rv = client.get("/api/stream-progress/task_123")

        assert rv.status_code == 500
        data = rv.get_json()
        assert data["status"] == 500
        assert data["code"] == "FAILED_TO_RETRIEVE_RESULTS"

    def test_stream_progress_returns_200_with_sse_headers(self, fake_progress, client):
        """Test that stream_progress returns 200 with proper SSE headers."""
        fake_progress([snapshot(1, 100, "Complete")])

        rv = client.get("/api/stream-progress/task_123")

        assert rv.status_code == 200
        assert rv.content_type.startswith("text/event-stream")
        assert rv.headers.get("Cache-Control") == "no-cache"
        assert rv.headers.get("Connection") == "keep-alive"

    def test_stream_sends_each_change_and_completes_on_100_percent(self, fake_progress, client):
        """Every change is sent once, including a same-step message such as a rate-limit wait."""
        waiting = snapshot(1, 25, "OpenDota limit reached, retrying account 7 in 20s", {"retry_in": 20})
        fake_progress(
            [
                snapshot(0, 0, "Starting"),
                snapshot(1, 25, "Step 1"),
                snapshot(1, 25, "Step 1"),  # unchanged, not sent again
                waiting,
                snapshot(2, 100, "Complete", {"successful": 1, "total": 1}),
            ]
        )

        rv = client.get("/api/stream-progress/task_123")

        lines = stream_lines(rv)
        assert [(line["step"], line["message"]) for line in lines] == [
            (0, "Starting"),
            (1, "Step 1"),
            (1, "OpenDota limit reached, retrying account 7 in 20s"),
            (2, "Complete"),
        ]
        assert lines[2]["data"] == {"retry_in": 20}
        assert lines[-1]["progress"] == 100
        assert lines[-1]["data"] == {"successful": 1, "total": 1}

    def test_stream_completes_on_error_state(self, fake_progress, client):
        """Test that stream completes when progress is -1 (error state)."""
        fake_progress([snapshot(0, 0, "Starting"), snapshot(-1, -1, "Task error: boom", {"error": True})])

        rv = client.get("/api/stream-progress/task_123")

        lines = stream_lines(rv)
        assert lines[-1] == {"step": -1, "message": "Task error: boom", "progress": -1, "data": {"error": True}}

    def test_stream_waits_for_progress_signal_between_reads(self, fake_progress, client):
        """The stream subscribes before reading, waits on the signal instead of sleeping, and unsubscribes."""
        progress = fake_progress([snapshot(0, 0), snapshot(1, 50), snapshot(2, 100)])

        with patch("backend.dota_bet_analyzer.time.sleep") as mock_sleep:
            rv = client.get("/api/stream-progress/task_123")
            stream_lines(rv)

        mock_sleep.assert_not_called()
        progress.subscription.subscribe.assert_called_once_with("progress-updates:task_123")
        assert progress.subscription.get_message.call_count == 2
        progress.subscription.get_message.assert_called_with(timeout=1.0)
        progress.subscription.close.assert_called_once()

    def test_stream_times_out_after_idle_limit(self, fake_progress, client):
        """With no changes for 30s the stream sends a timeout line and ends."""
        progress = fake_progress([snapshot(1, 10)], wait_seconds=1.0)

        rv = client.get("/api/stream-progress/task_123")

        lines = stream_lines(rv)
        assert len(lines) == 2
        assert lines[-1]["progress"] == -1
        assert lines[-1]["message"] == "Task timed out - no progress updates for 30s"
        assert lines[-1]["data"] == {"error": True, "timeout": True}
        # One blocking wait per second of idle time, not a busy loop
        assert progress.subscription.get_message.call_count == 31

    def test_stream_times_out_on_max_runtime(self, fake_progress, client):
        """A task that keeps changing but never completes is cut off after 120s."""
        fake_progress([snapshot(step, 50, f"Step {step}") for step in range(200)], wait_seconds=1.0)

        rv = client.get("/api/stream-progress/task_123")

        lines = stream_lines(rv)
        assert lines[-1]["message"] == "Task exceeded maximum runtime (120s)"
        assert lines[-1]["data"]["timeout"] is True

    def test_stream_handles_json_decode_error(self, fake_progress, client):
        """Test that stream handles invalid JSON gracefully."""
        progress = fake_progress([b"invalid json {{{"])

        rv = client.get("/api/stream-progress/task_123")

        lines = stream_lines(rv)
        assert lines[-1]["progress"] == -1
        assert "invalid progress data" in lines[-1]["message"].lower()
        assert lines[-1]["data"]["error"] is True
        progress.subscription.close.assert_called_once()

    def test_stream_handles_stream_exception(self, fake_progress, client):
        """Test that stream handles unexpected exceptions gracefully."""
        fake_progress([snapshot(0, 0), RuntimeError("Unexpected error")])

        rv = client.get("/api/stream-progress/task_123")

        lines = stream_lines(rv)
        assert lines[-1]["progress"] == -1
        assert lines[-1]["message"] == "Stream error: Unexpected error"
        assert lines[-1]["data"]["error"] is True


def test_progress_is_rounded_to_one_decimal():
    from backend import task_store

    with patch.object(task_store, "redis_client") as redis:
        task_store.update_progress("task_1", 5, "Got Player rank", 100 * 5 / 12)

    stored = json.loads(redis.setex.call_args.args[2])
    assert stored["progress"] == 41.7


def test_update_progress_signals_open_streams_after_storing():
    """The progress signal goes out after the snapshot is stored, so a woken stream reads the new one."""
    from backend import task_store

    with patch.object(task_store, "redis_client") as redis:
        task_store.update_progress("task_1", 2, "Got matches", 50)

    assert [call[0] for call in redis.method_calls] == ["setex", "publish"]
    redis.publish.assert_called_once_with("progress-updates:task_1", "2")

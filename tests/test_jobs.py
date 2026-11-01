"""Tests for the background cache jobs (backend.jobs) and GET /api/jobs, POST /api/jobs/{name}/run.

Redis is an in-memory fake and Celery is never reached (apply_async is mocked); jobs never request OpenDota.
"""

import time
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest
import redis

from backend import jobs
from backend.jobs import (
    FAILED,
    IDLE,
    QUEUED,
    RETRY_AFTER_FAILURE_SECONDS,
    Job,
    JobRunningError,
    UnknownJobError,
    get_synced_at,
    is_due,
    job_status,
    queue_due_jobs,
    queue_due_jobs_on_startup,
    queue_job,
    queue_job_if_due,
    run_job,
)
from backend.pro_players import get_d2ba_db


class FakeRedis:
    """The few Redis commands the jobs use (expiry is not simulated: delete a key to expire it)."""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    def get(self, key: str) -> Optional[bytes]:
        value = self.data.get(key)
        return None if value is None else str(value).encode()

    def set(self, key: str, value: Any, nx: bool = False, ex: Optional[int] = None):
        if nx and key in self.data:
            return None
        self.data[key] = value
        return True

    def delete(self, key: str) -> None:
        self.data.pop(key, None)


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch) -> FakeRedis:
    fake = FakeRedis()
    monkeypatch.setattr(jobs, "redis_client", fake)
    return fake


@pytest.fixture(autouse=True)
def mock_apply_async():
    """Queueing never reaches the Celery broker."""
    with patch.object(jobs.run_job_task, "apply_async") as mock:
        yield mock


@pytest.fixture
def test_job(monkeypatch) -> MagicMock:
    """Replace the teams job with one whose run is a mock (no OpenDota request)."""
    run = MagicMock(return_value="Stored 2 teams")
    monkeypatch.setitem(jobs.JOBS, "teams", Job(name="teams", title="Teams list", run=run, stale_after=3600))
    return run


def set_synced_at(app, name: str, synced_at: int) -> None:
    with app.app_context():
        db = get_d2ba_db()
        db.execute("INSERT INTO sync_state (name, synced_at) VALUES (?, ?)", (name, synced_at))
        db.commit()


def lock_token(fake: FakeRedis, name: str) -> str:
    return str(fake.data[f"job:{name}:lock"])


def test_registry_has_every_cache_job():
    assert list(jobs.JOBS) == ["pro_players", "heroes", "teams", "hero_meta", "matches"]
    with pytest.raises(UnknownJobError):
        jobs.get_job("nope")


def test_never_run_job_is_idle_and_due(app, test_job):
    with app.app_context():
        status = job_status(jobs.JOBS["teams"])
        assert is_due(jobs.JOBS["teams"])
    assert status == {
        "name": "teams",
        "title": "Teams list",
        "state": IDLE,
        "progress": 0,
        "message": None,
        "last_success": None,
        "last_error": None,
        "last_error_at": None,
        "next_run": None,
    }


def test_job_is_due_again_after_stale_after(app, test_job):
    now = int(time.time())
    set_synced_at(app, "teams", now - 600)
    job = jobs.JOBS["teams"]
    with app.app_context():
        assert job_status(job, now)["next_run"] == now - 600 + 3600
        assert not is_due(job, now)
        assert is_due(job, now + 3000)


def test_queue_job_locks_and_sends_to_background_queue(app, test_job, fake_redis, mock_apply_async):
    with app.app_context():
        status = queue_job("teams")
        assert status["state"] == QUEUED
        assert not is_due(jobs.JOBS["teams"])
        with pytest.raises(JobRunningError):
            queue_job("teams")
    token = lock_token(fake_redis, "teams")
    mock_apply_async.assert_called_once_with(args=["teams", token], queue="background")


def test_queue_job_failure_releases_lock(app, test_job, fake_redis, mock_apply_async):
    mock_apply_async.side_effect = ConnectionError("broker down")
    with app.app_context(), pytest.raises(ConnectionError):
        queue_job("teams")
    assert "job:teams:lock" not in fake_redis.data
    with app.app_context():
        assert job_status(jobs.JOBS["teams"])["state"] == IDLE


def test_expired_lock_makes_queued_job_idle(app, test_job, fake_redis):
    with app.app_context():
        queue_job("teams")
        fake_redis.delete("job:teams:lock")
        assert job_status(jobs.JOBS["teams"])["state"] == IDLE
        assert is_due(jobs.JOBS["teams"])


def test_run_job_records_success_and_releases_lock(app, test_job, fake_redis):
    with app.app_context():
        queue_job("teams")
        assert run_job("teams", lock_token(fake_redis, "teams")) == "Stored 2 teams"
        status = job_status(jobs.JOBS["teams"])
        assert get_synced_at("teams") is not None
    test_job.assert_called_once()
    assert status["state"] == IDLE
    assert status["progress"] == 100
    assert status["message"] == "Stored 2 teams"
    assert status["next_run"] is not None
    assert "job:teams:lock" not in fake_redis.data


def test_failed_job_records_error_and_waits_before_retry(app, test_job, fake_redis):
    test_job.side_effect = ConnectionError("OpenDota daily limit reached")
    with app.app_context():
        queue_job("teams")
        assert run_job("teams", lock_token(fake_redis, "teams")) is None
        job = jobs.JOBS["teams"]
        status = job_status(job)
        assert get_synced_at("teams") is None
        assert not is_due(job)
        assert is_due(job, time.time() + RETRY_AFTER_FAILURE_SECONDS + 1)
    assert status["state"] == FAILED
    assert status["last_error"] == "OpenDota daily limit reached"
    assert status["next_run"] >= status["last_error_at"] + RETRY_AFTER_FAILURE_SECONDS
    assert "job:teams:lock" not in fake_redis.data


def test_run_with_old_token_is_skipped(app, test_job):
    with app.app_context():
        queue_job("teams")
        assert run_job("teams", "old-token") is None
    test_job.assert_not_called()


def test_queue_due_jobs_skips_fresh_ones(app, mock_apply_async):
    set_synced_at(app, "heroes", int(time.time()))
    with app.app_context():
        assert queue_due_jobs() == ["pro_players", "teams", "hero_meta", "matches"]
        assert queue_due_jobs() == []  # Already queued
    assert mock_apply_async.call_count == 4


def test_queue_if_due_logs_redis_errors(app, test_job, mock_apply_async):
    with app.app_context(), patch.object(jobs, "_read_status", side_effect=redis.ConnectionError("down")):
        assert queue_job_if_due("teams") is False
    mock_apply_async.assert_not_called()


def test_redis_down_reads_as_idle(app, test_job, monkeypatch):
    broken = MagicMock()
    broken.get.side_effect = redis.ConnectionError("down")
    monkeypatch.setattr(jobs, "redis_client", broken)
    with app.app_context():
        assert job_status(jobs.JOBS["teams"])["state"] == IDLE


def test_startup_queues_due_jobs(app, mock_apply_async):
    assert queue_due_jobs_on_startup(app) == ["pro_players", "heroes", "teams", "hero_meta", "matches"]


def test_startup_skips_worker_and_reloader_parent(app, mock_apply_async, monkeypatch):
    monkeypatch.setattr(jobs, "_in_worker", True)
    assert queue_due_jobs_on_startup(app) == []
    monkeypatch.setattr(jobs, "_in_worker", False)
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
    app.debug = True
    assert queue_due_jobs_on_startup(app) == []
    mock_apply_async.assert_not_called()


def test_teams_job_fails_when_opendota_returns_no_teams(app):
    with app.app_context(), patch("backend.teams_sync.fetch_teams_from_api", return_value=[]):
        with pytest.raises(ValueError, match="no teams"):
            jobs.JOBS["teams"].run()


def test_pro_players_and_heroes_jobs_store_data(app):
    players = [{"account_id": 1, "name": "p", "team_id": 2, "team_name": "t"}]
    heroes = [{"hero_id": 1, "name": "npc_dota_hero_antimage", "localized_name": "Anti-Mage", "icon": ""}]
    with (
        app.app_context(),
        patch("backend.pro_players.fetch_pro_players_from_api", return_value=players) as fetch_players,
        patch("backend.heroes.fetch_heroes_from_api", return_value=heroes) as fetch_heroes,
    ):
        assert jobs.JOBS["pro_players"].run() == "Stored 1 pro players"
        assert jobs.JOBS["heroes"].run() == "Stored 1 heroes"
    fetch_players.assert_called_once_with(background=True)
    fetch_heroes.assert_called_once_with(background=True)


def test_hero_meta_and_matches_jobs_refresh_their_caches(app):
    with (
        patch("backend.meta.refresh_hero_stats", return_value=([{"hero_id": 1}], 100)) as refresh_meta,
        patch("backend.matches.refresh_matches", return_value=[{}, {}]) as refresh_matches,
    ):
        assert jobs.JOBS["hero_meta"].run() == "Cached stats of 1 heroes"
        assert jobs.JOBS["matches"].run() == "Cached 2 series"
    refresh_meta.assert_called_once_with(background=True)
    refresh_matches.assert_called_once_with(background=True)


def test_hero_meta_job_fails_without_hero_stats():
    with patch("backend.meta.refresh_hero_stats", return_value=([], 100)):
        with pytest.raises(ValueError, match="no hero stats"):
            jobs.JOBS["hero_meta"].run()


def test_beat_sends_due_jobs_check_every_minute_to_background_queue():
    from backend.celery_app import BACKGROUND_QUEUE, celery

    entry = celery.conf.beat_schedule["check-due-jobs"]
    assert entry["task"] == jobs.check_due_jobs_task.name
    assert entry["schedule"] == 60
    assert entry["options"] == {"queue": BACKGROUND_QUEUE, "expires": 60}


def test_check_due_jobs_task_queues_due_jobs(app, mock_apply_async):
    set_synced_at(app, "heroes", int(time.time()))
    with patch("backend.create_app", return_value=app):
        assert jobs.check_due_jobs_task.run() == ["pro_players", "teams", "hero_meta", "matches"]
    assert mock_apply_async.call_count == 4


def test_get_jobs_endpoint(client):
    rv = client.get("/api/jobs")
    assert rv.status_code == 200
    data = rv.get_json()
    assert [job["name"] for job in data] == ["pro_players", "heroes", "teams", "hero_meta", "matches"]
    assert data[0]["state"] == IDLE


def test_get_jobs_database_error(client):
    with patch("backend.dota_bet_analyzer.list_job_statuses", side_effect=RuntimeError("disk")):
        rv = client.get("/api/jobs")
    assert rv.status_code == 500
    assert rv.get_json()["code"] == "FAILED_TO_READ_JOBS"


def test_run_endpoint_queues_job(client, mock_apply_async):
    rv = client.post("/api/jobs/heroes/run")
    assert rv.status_code == 202
    assert rv.get_json()["state"] == QUEUED
    mock_apply_async.assert_called_once()


def test_run_endpoint_errors(client, mock_apply_async):
    assert client.post("/api/jobs/nope/run").get_json()["code"] == "JOB_NOT_FOUND"
    assert client.post("/api/jobs/nope/run").status_code == 404
    client.post("/api/jobs/heroes/run")
    rv = client.post("/api/jobs/heroes/run")
    assert rv.status_code == 409
    assert rv.get_json()["code"] == "JOB_RUNNING"
    mock_apply_async.side_effect = ConnectionError("broker down")
    rv = client.post("/api/jobs/teams/run")
    assert rv.status_code == 503
    assert rv.get_json()["code"] == "FAILED_TO_QUEUE_JOB"

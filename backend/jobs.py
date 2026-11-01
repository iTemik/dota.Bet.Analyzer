"""Background jobs that keep the caches (pro players, heroes, teams list, hero meta, Liquipedia matches) up to date.

Each job is declared once in JOBS with how old its data may get (`stale_after`). A due job is queued as a Celery
task on the `background` queue, served by its own worker, so Compare never waits behind it. Jobs are queued:
- every minute by Celery Beat (check_due_jobs_task) for every due job
- at startup (Flask server only) for every due job
- on team search and matches requests for the teams list
- by POST /api/jobs/{name}/run (`?full=true` for the complete teams list)

State in Redis (db 1):
- `job:<name>:lock`: held from queueing until the job ends, so a job never runs twice at once; it expires after
  LOCK_TTL_SECONDS in case a worker dies or is not running
- `job:<name>`: JSON with state (idle, queued, running, failed), progress, message, last error and its time;
  while a running job waits for the request limiter longer than the normal pace, its message says so

The time of the last success is kept in the `sync_state` table, so a Redis restart does not resync everything.
A failed job is not queued again on its own for RETRY_AFTER_FAILURE_SECONDS. Jobs request OpenDota as background
requests: they let user requests go first and stop when the daily budget is used up.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional

import redis
from celery.signals import worker_init  # type: ignore[import-untyped]
from flask import Flask
from werkzeug.serving import is_running_from_reloader

from backend import cache
from backend.celery_app import BACKGROUND_QUEUE, celery
from backend.logging_config import setup_logging
from backend.pro_players import get_d2ba_db
from backend.rate_limit import report_waits

logger = setup_logging(__name__)

LOCK_TTL_SECONDS = 30 * 60  # Longest a job may stay queued or running before it can be queued again
RETRY_AFTER_FAILURE_SECONDS = 10 * 60  # No new automatic run this soon after a failed one

IDLE, QUEUED, RUNNING, FAILED = "idle", "queued", "running", "failed"

_in_worker = False  # True inside a Celery worker, which never queues jobs at startup


@worker_init.connect
def _mark_worker(**_: Any) -> None:
    """Remember that this process is a Celery worker (it creates the Flask app too, for the database)."""
    global _in_worker
    _in_worker = True


class JobRunningError(Exception):
    """The job is already queued or running."""


class UnknownJobError(Exception):
    """No job has this name."""


def _run_pro_players() -> str:
    from backend.pro_players import fetch_pro_players_from_api, store_pro_players

    players = fetch_pro_players_from_api(background=True)
    if not players:
        raise ValueError("OpenDota returned no pro players")
    return f"Stored {store_pro_players(players)} pro players"


def _run_heroes() -> str:
    from backend.heroes import fetch_heroes_from_api, store_heroes

    heroes = fetch_heroes_from_api(background=True)
    if not heroes:
        raise ValueError("OpenDota returned no heroes")
    return f"Stored {store_heroes(heroes)} heroes"


def _run_hero_meta() -> str:
    from backend.meta import refresh_hero_stats

    heroes, _ = refresh_hero_stats(background=True)
    if not heroes:
        raise ValueError("OpenDota returned no hero stats")
    return f"Cached stats of {len(heroes)} heroes"


def _run_matches() -> str:
    from backend.matches import refresh_matches

    return f"Cached {len(refresh_matches(background=True))} series"


def _run_teams(full: bool = False) -> str:
    from backend.teams_sync import run_teams_sync

    count = run_teams_sync(full=full)
    if not count and get_synced_at("teams") is None:
        raise ValueError("OpenDota returned no teams")
    return f"Stored {count} teams" if count else "No new teams data"


@dataclass(frozen=True)
class Job:
    """A cache job.

    Attributes:
        name: Job name, also its `sync_state.name`
        title: Shown to the user, e.g. "Teams list"
        run: Updates the cache inside an app context and returns a short result message; raises on failure
        stale_after: Seconds after the last success when the job is due again
        run_full: Slower complete update, queued only on request (POST /api/jobs/{name}/run?full=true); None when
            the job has none
    """

    name: str
    title: str
    run: Callable[[], str]
    stale_after: int
    run_full: Optional[Callable[[], str]] = None


JOBS: dict[str, Job] = {
    job.name: job
    for job in (
        # Team assignments of players change often, and the whole list is one request
        Job(name="pro_players", title="Pro players", run=_run_pro_players, stale_after=24 * 3600),
        # New heroes are rare; one request
        Job(name="heroes", title="Heroes", run=_run_heroes, stale_after=7 * 86400),
        # Incremental: 2 explorer requests (full ~22 only when the table is empty)
        Job(
            name="teams",
            title="Teams list",
            run=_run_teams,
            stale_after=24 * 3600,
            run_full=lambda: _run_teams(full=True),  # ~22 requests: every /teams page
        ),
        # One /heroStats request; OpenDota recomputes it a few times a day (Meta tab)
        Job(name="hero_meta", title="Hero meta", run=_run_hero_meta, stale_after=3600),
        # One Liquipedia parse (their limit: 1 per 30 s); upcoming and finished series of the main page
        Job(name="matches", title="Matches", run=_run_matches, stale_after=10 * 60),
    )
}


def get_job(name: str) -> Job:
    """The job with this name.

    Raises:
        UnknownJobError: If there is no such job
    """
    job = JOBS.get(name)
    if job is None:
        raise UnknownJobError(f"Unknown job: {name}")
    return job


def get_synced_at(name: str) -> Optional[int]:
    """Time of the last success of a job (sync_state), in unix seconds, or None when it never succeeded."""
    row = get_d2ba_db().execute("SELECT synced_at FROM sync_state WHERE name = ?", (name,)).fetchone()
    return row["synced_at"] if row else None


def _set_synced_at(name: str, synced_at: int) -> None:
    db = get_d2ba_db()
    db.execute(
        """
        INSERT INTO sync_state (name, synced_at) VALUES (?, ?)
        ON CONFLICT(name) DO UPDATE SET synced_at = excluded.synced_at
        """,
        (name, synced_at),
    )
    db.commit()


def _status_key(name: str) -> str:
    return f"job:{name}"


def _lock_key(name: str) -> str:
    return f"job:{name}:lock"


def _decode(value: Any) -> Optional[str]:
    if value is None:
        return None
    return value.decode() if isinstance(value, bytes) else str(value)


def _read_status(name: str) -> dict[str, Any]:
    """Stored status of a job (empty when none or Redis is unavailable)."""
    try:
        raw = _decode(cache.redis_client.get(_status_key(name)))
        locked = cache.redis_client.get(_lock_key(name)) is not None
    except redis.RedisError as e:
        logger.warning(f"Could not read the status of job {name}: {e}")
        return {}
    status: dict[str, Any] = json.loads(raw) if raw else {}
    if status.get("state") in (QUEUED, RUNNING) and not locked:
        status["state"] = IDLE  # The lock expired: the worker died or was never started
    return status


def _write_status(name: str, **fields: Any) -> None:
    """Merge fields into a job's status; Redis errors are logged."""
    try:
        raw = _decode(cache.redis_client.get(_status_key(name)))
        status = json.loads(raw) if raw else {}
        status.update(fields, updated_at=int(time.time()))
        cache.redis_client.set(_status_key(name), json.dumps(status))
    except redis.RedisError as e:
        logger.warning(f"Could not save the status of job {name}: {e}")


def _running_message(job: Job) -> str:
    return f"Updating {job.title.lower()}"


def job_status(job: Job, now: Optional[float] = None) -> dict[str, Any]:
    """Status of one job, as returned by GET /api/jobs.

    Args:
        job: The job
        now: Current unix time (defaults to time.time())

    Returns:
        name, title, state, progress (0-100), message, last_success, last_error, last_error_at and next_run
        (unix seconds when the job is due again; None when it is due now)
    """
    current = time.time() if now is None else now
    status = _read_status(job.name)
    last_success = get_synced_at(job.name)
    last_error_at = status.get("last_error_at")
    next_run = last_success + job.stale_after if last_success is not None else None
    if last_error_at is not None and (last_success is None or last_error_at > last_success):
        next_run = max(next_run or 0, last_error_at + RETRY_AFTER_FAILURE_SECONDS)
    if next_run is not None and next_run <= current:
        next_run = None
    message = status.get("message")
    if status.get("state") == RUNNING and (status.get("wait_until") or current) < current:
        message = _running_message(job)  # The wait for the request limit is over
    return {
        "name": job.name,
        "title": job.title,
        "state": status.get("state", IDLE),
        "progress": status.get("progress", 0),
        "message": message,
        "last_success": last_success,
        "last_error": status.get("last_error"),
        "last_error_at": last_error_at,
        "next_run": next_run,
    }


def list_job_statuses() -> list[dict[str, Any]]:
    """Status of every job, in JOBS order (see job_status)."""
    return [job_status(job) for job in JOBS.values()]


def data_status() -> dict[str, Any]:
    """Status of every job and today's OpenDota request budget, as sent by GET /api/jobs/stream. No OpenDota request.

    Returns:
        jobs: list_job_statuses()
        budget: used (OpenDota requests today, UTC, by every process; None when Redis cannot be reached) and limit
            (daily budget of background requests; 0 = no budget)
    """
    from backend.opendota import OPENDOTA_LIMITER

    return {
        "jobs": list_job_statuses(),
        "budget": {"used": OPENDOTA_LIMITER.used_today(), "limit": OPENDOTA_LIMITER.daily_limit},
    }


def is_due(job: Job, now: Optional[float] = None) -> bool:
    """Whether a job should be queued on its own: not queued or running, and its data is stale.

    Data is stale when the job never succeeded or its last success is `stale_after` old; a failed job waits
    RETRY_AFTER_FAILURE_SECONDS before it is due again.
    """
    status = job_status(job, now)
    return status["state"] not in (QUEUED, RUNNING) and status["next_run"] is None


def queue_job(name: str, full: bool = False) -> dict[str, Any]:
    """Queue a job on the background queue.

    Args:
        name: Job name
        full: Run the job's `run_full` instead of `run` (only for jobs that have one)

    Returns:
        The job's status after queueing

    Raises:
        UnknownJobError: If there is no such job
        JobRunningError: If the job is already queued or running
        redis.RedisError, kombu errors: If Redis or the Celery broker cannot be reached
    """
    job = get_job(name)
    token = uuid.uuid4().hex
    if not cache.redis_client.set(_lock_key(name), token, nx=True, ex=LOCK_TTL_SECONDS):
        raise JobRunningError(f"{job.title} update is already running")
    try:
        kind = "full update" if full else "update"
        _write_status(name, state=QUEUED, progress=0, message=f"{job.title} {kind} queued")
        options: dict[str, Any] = {"kwargs": {"full": True}} if full else {}
        run_job_task.apply_async(args=[name, token], queue=BACKGROUND_QUEUE, **options)
    except Exception:
        _release(name, token)
        _write_status(name, state=IDLE, message=None)
        raise
    logger.info(f"Queued job {name}")
    return job_status(job)


def queue_job_if_due(name: str) -> bool:
    """Queue a job when it is due; errors are logged (callers never fail because of a cache job).

    Returns:
        True when the job was queued
    """
    try:
        if not is_due(get_job(name)):
            return False
        queue_job(name)
        return True
    except JobRunningError:
        return False
    except Exception as e:
        logger.error(f"Could not queue job {name}: {e}")
        return False


def queue_due_jobs() -> list[str]:
    """Queue every due job.

    Returns:
        Names of the queued jobs
    """
    return [name for name in JOBS if queue_job_if_due(name)]


def queue_due_jobs_on_startup(app: Flask) -> list[str]:
    """Queue every due job when the Flask server starts.

    Skipped in Celery workers (they create the app for its database) and in the watching parent of the debug
    reloader (only the serving child queues).

    Args:
        app: Flask app

    Returns:
        Names of the queued jobs
    """
    if _in_worker or (app.debug and not is_running_from_reloader()):
        return []
    try:
        with app.app_context():
            return queue_due_jobs()
    except sqlite3.Error as e:
        logger.error(f"Could not check the cache jobs at startup: {e}")
        return []


def _release(name: str, token: str) -> None:
    """Release a job lock when this run still holds it."""
    try:
        if _decode(cache.redis_client.get(_lock_key(name))) == token:
            cache.redis_client.delete(_lock_key(name))
    except redis.RedisError as e:
        logger.warning(f"Could not release the lock of job {name}: {e}")


def run_job(name: str, token: str, full: bool = False) -> Optional[str]:
    """Run a queued job inside an app context, record its status and release its lock.

    A run whose lock expired or was taken by a newer queueing is skipped (an old message left in the queue).

    Args:
        name: Job name
        token: Lock token from queue_job
        full: Run the job's `run_full` (falls back to `run` when the job has none)

    Returns:
        The result message, or None when the run was skipped or failed
    """
    job = get_job(name)
    try:
        if _decode(cache.redis_client.get(_lock_key(name))) != token:
            logger.info(f"Skipping job {name}: its queueing expired or a newer one holds the lock")
            return None
    except redis.RedisError as e:
        logger.warning(f"Could not check the lock of job {name}, running it anyway: {e}")
    _write_status(name, state=RUNNING, progress=0, message=_running_message(job), wait_until=None)
    message: Optional[str] = None

    def report_wait(seconds: int) -> None:
        _write_status(
            name,
            message=f"Updating {job.title.lower()}: waiting for the request limit, {seconds} s",
            wait_until=int(time.time()) + seconds,
        )

    try:
        with report_waits(report_wait):
            message = (job.run_full or job.run)() if full else job.run()
        _set_synced_at(name, int(time.time()))
    except Exception as e:
        logger.error(f"Job {name} failed: {e}")
        message = None
        _write_status(
            name,
            state=FAILED,
            progress=0,
            message=f"{job.title} update failed",
            last_error=str(e),
            last_error_at=int(time.time()),
        )
    else:
        logger.info(f"Job {name} done: {message}")
        _write_status(name, state=IDLE, progress=100, message=message)
    finally:
        _release(name, token)
    return message


@celery.task(name="backend.jobs.check_due_jobs_task", ignore_result=True)
def check_due_jobs_task() -> list[str]:
    """Celery task sent every minute by Celery Beat (see CHECK_DUE_JOBS_SCHEDULE): queue every due job.

    Returns:
        Names of the queued jobs
    """
    from backend import create_app

    with create_app().app_context():
        return queue_due_jobs()


@celery.task(name="backend.jobs.run_job_task")
def run_job_task(name: str, token: str, full: bool = False) -> Optional[str]:
    """Celery task of one cache job (background queue); see run_job."""
    from backend import create_app

    with create_app().app_context():
        return run_job(name, token, full)

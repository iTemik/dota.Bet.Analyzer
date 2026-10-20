"""Redis storage for task progress, task results and cached OpenDota player data."""

import json
import time

import redis
from redis.client import PubSub

from backend.config import Config
from backend.logging_config import setup_logging
from backend.opendota import WaitCallback
from backend.stats import MatchStats, get_matches, get_rank

logger = setup_logging(__name__)

# Redis for progress, results and the player cache
redis_client = redis.Redis(host=Config.REDIS_HOST, port=Config.REDIS_PORT, db=1)


def _progress_channel(task_id: str) -> str:
    """Pub/sub channel that signals a task's progress changed."""
    return f"progress-updates:{task_id}"


def update_progress(task_id: str, step: int, message: str, progress: float, data: dict | None = None) -> None:
    """Update task progress in Redis (lightweight - no heavy data).

    Args:
        task_id: Unique task identifier
        step: Current step number
        message: Progress message
        progress: Progress percentage (0-100) or -1 for error; rounded to 1 decimal place
        data: Additional data to store (optional, should be lightweight)
    """
    progress = round(progress, 1)
    try:
        progress_data = {
            "step": step,
            "message": message,
            "progress": progress,
            "data": data or {},
            "timestamp": time.time(),
        }
        redis_client.setex(f"progress:{task_id}", 3600, json.dumps(progress_data))  # Expire after 1 hour
        # Wake open progress streams; they read the snapshot above, so the message carries no data
        redis_client.publish(_progress_channel(task_id), str(step))
        logger.debug(f"Progress updated for task {task_id}: {message} ({progress}%)")
    except Exception as e:
        # Log error but don't fail the task if Redis is unavailable
        logger.warning(f"Failed to update progress for task {task_id}: {e}")


class ProgressReporter:
    """Reports a task's progress, keeping the step counter and percentage in one place.

    Args:
        task_id: Unique task identifier
        total_steps: Number of steps the task reports before it is done
    """

    def __init__(self, task_id: str, total_steps: int) -> None:
        self.task_id = task_id
        self.total_steps = total_steps
        self.step = 0

    def report(self, message: str, data: dict | None = None) -> None:
        """Report a message for the current step.

        Args:
            message: Progress message
            data: Additional lightweight data (optional)
        """
        update_progress(self.task_id, self.step, message, 100 * (self.step / self.total_steps), data)

    def start(self, message: str) -> None:
        """Report the initial step (step 0).

        Args:
            message: Progress message
        """
        self.report(message)

    def next(self) -> None:
        """Advance to the next step."""
        self.step += 1

    def waiting(self, delay: int, account_id: int) -> None:
        """Report that an OpenDota request for an account is postponed by the rate limit.

        Args:
            delay: Seconds until the retry
            account_id: Player account ID being fetched
        """
        self.report(
            f"OpenDota limit reached, retrying account {account_id} in {delay}s",
            {"account_id": account_id, "retry_in": delay},
        )

    def done(self, message: str, data: dict | None = None) -> None:
        """Report the last step at 100%.

        Args:
            message: Progress message
            data: Additional lightweight data (optional)
        """
        update_progress(self.task_id, self.total_steps, message, 100, data)

    def fail(self, exc: Exception) -> None:
        """Mark the task failed (step and progress -1).

        Args:
            exc: The error that stopped the task
        """
        update_progress(self.task_id, -1, f"Task error: {exc!s}", -1, {"error": True})


def store_results(task_id: str, results_data: dict) -> None:
    """Store heavy computation results in Redis (separate from progress).

    Args:
        task_id: Unique task identifier
        results_data: Heavy results data (will be stored separately)
    """
    try:
        redis_client.setex(f"results:{task_id}", 3600, json.dumps(results_data))  # Expire after 1 hour
        logger.debug(f"Results stored for task {task_id}")
    except Exception as e:
        logger.warning(f"Failed to store results for task {task_id}: {e}")


def progress_exists(task_id: str) -> bool:
    """Check whether a task has stored any progress.

    Args:
        task_id: Unique task identifier

    Returns:
        True if progress is stored for the task

    Raises:
        Exception: If Redis is unavailable
    """
    return redis_client.get(f"progress:{task_id}") is not None


def load_results(task_id: str) -> dict | None:
    """Load a task's stored results.

    Args:
        task_id: Unique task identifier

    Returns:
        Decoded results or None if not stored

    Raises:
        Exception: If Redis is unavailable or the stored value is not valid JSON
    """
    results_data = redis_client.get(f"results:{task_id}")
    if not results_data:
        return None
    results: dict = json.loads(results_data)
    return results


PLAYER_MATCHES_CACHE_TTL = 60 * 60  # 1 hour
PLAYER_RANK_CACHE_TTL = 24 * 60 * 60  # 1 day


def _cache_get(key: str) -> object | None:
    """Read a JSON value from the Redis cache (None if missing or Redis is unavailable).

    Args:
        key: Cache key

    Returns:
        Decoded JSON value or None
    """
    try:
        raw = redis_client.get(key)
        if isinstance(raw, (bytes, str)):
            value: object = json.loads(raw)
            return value
    except Exception as e:
        logger.debug(f"Cache read failed for {key}: {e}")
    return None


def _cache_set(key: str, ttl: int, value: object) -> None:
    """Write a JSON value to the Redis cache, ignoring errors.

    Args:
        key: Cache key
        ttl: Time to live in seconds
        value: JSON-serializable value
    """
    try:
        redis_client.setex(key, ttl, json.dumps(value))
    except Exception as e:
        logger.debug(f"Cache write failed for {key}: {e}")


def get_matches_cached(account_id: int, days: int, on_wait: WaitCallback | None = None) -> list[MatchStats]:
    """Fetch player matches, cached in Redis for PLAYER_MATCHES_CACHE_TTL.

    Args:
        account_id: Player account ID
        days: Number of days of match history
        on_wait: Called with the delay in seconds when the request is postponed by the OpenDota limits

    Returns:
        List of MatchStats
    """
    key = f"opendota:matches:{account_id}:{days}"
    cached = _cache_get(key)
    if isinstance(cached, list):
        try:
            return [MatchStats(**item) for item in cached]
        except Exception as e:
            logger.debug(f"Ignoring malformed cached matches for {account_id}: {e}")
    matches = get_matches(account_id=account_id, days=days, on_wait=on_wait)
    _cache_set(key, PLAYER_MATCHES_CACHE_TTL, [m.model_dump() for m in matches])
    return matches


def get_rank_cached(account_id: int, on_wait: WaitCallback | None = None) -> int | None:
    """Fetch player leaderboard rank, cached in Redis for PLAYER_RANK_CACHE_TTL.

    Args:
        account_id: Player account ID
        on_wait: Called with the delay in seconds when the request is postponed by the OpenDota limits

    Returns:
        Leaderboard rank or None
    """
    key = f"opendota:rank:{account_id}"
    cached = _cache_get(key)
    if isinstance(cached, dict) and "rank" in cached:
        rank = cached["rank"]
        return rank if isinstance(rank, int) else None
    rank = get_rank(account_id, on_wait=on_wait)
    _cache_set(key, PLAYER_RANK_CACHE_TTL, {"rank": rank})
    return rank


def subscribe_progress(task_id: str) -> PubSub:
    """Subscribe to a task's progress signals (published by update_progress).

    Args:
        task_id: Unique task identifier

    Returns:
        Subscription to pass to wait_for_progress; close it when done

    Raises:
        Exception: If Redis is unavailable
    """
    subscription = redis_client.pubsub(ignore_subscribe_messages=True)
    subscription.subscribe(_progress_channel(task_id))
    return subscription


def wait_for_progress(subscription: PubSub, timeout: float) -> None:
    """Block until the task signals a progress change or the timeout passes.

    Args:
        subscription: Subscription from subscribe_progress
        timeout: Maximum seconds to wait

    Raises:
        Exception: If Redis is unavailable
    """
    subscription.get_message(timeout=timeout)


def read_progress(task_id: str) -> bytes | None:
    """Read a task's stored progress snapshot.

    Args:
        task_id: Unique task identifier

    Returns:
        Raw JSON snapshot or None if not stored

    Raises:
        Exception: If Redis is unavailable
    """
    progress: bytes | None = redis_client.get(f"progress:{task_id}")
    return progress

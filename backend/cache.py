"""The app's one Redis client (db 1) and the JSON cache helper used by every Redis cache.

Every module that keeps state in Redis db 1 (task progress and results, caches, job status, rate limiter) uses
`redis_client` from here, so tests can swap one object. The cache helpers never raise on Redis errors: when Redis
cannot be reached, values are fetched every time and nothing is stored.

A failed fetch can be cached too (`error_ttl`): it is stored as `{"error": message}` and raised again as
ConnectionError until it expires, so a broken page or API is not asked again on every request.
"""

import json
from collections.abc import Callable
from typing import Any, Optional

import redis

from backend.config import Config
from backend.logging_config import setup_logging

logger = setup_logging(__name__)

redis_client = redis.Redis(host=Config.REDIS_HOST, port=Config.REDIS_PORT, db=1)


def cache_get(key: str) -> Any:
    """Decoded JSON value stored under key, or None when missing, not JSON or Redis is unavailable.

    Args:
        key: Redis key

    Returns:
        Decoded JSON value or None
    """
    try:
        raw = redis_client.get(key)
        if isinstance(raw, (bytes, str)):
            return json.loads(raw)
    except Exception as e:
        logger.warning(f"Cache read failed for {key}: {e}")
    return None


def cache_set(key: str, ttl: int, value: Any) -> None:
    """Store a JSON value under key for ttl seconds; Redis errors are logged, not raised.

    Args:
        key: Redis key
        ttl: Time to live in seconds
        value: JSON-serializable value
    """
    try:
        redis_client.setex(key, ttl, json.dumps(value))
    except Exception as e:
        logger.warning(f"Cache write failed for {key}: {e}")


def _cached_error(value: Any) -> Optional[str]:
    """The message of a cached failure (a dict with only an "error" key), else None."""
    if isinstance(value, dict) and set(value) == {"error"}:
        return str(value["error"])
    return None


def cached_json(
    key: str,
    ttl: int,
    fetch: Callable[[], Any],
    error_ttl: Optional[int] = None,
    use: Optional[Callable[[Any], bool]] = None,
) -> Any:
    """Value cached under key, or fetched and cached for ttl seconds.

    Args:
        key: Redis key
        ttl: Seconds a fetched value is kept
        fetch: Returns the JSON-serializable value when it is not cached; must not return {"error": ...}
        error_ttl: When set, a ConnectionError or ValueError from fetch is cached this many seconds and raised
            again as ConnectionError from the cache; when None, errors are raised as they are and not cached
        use: Called with a cached value; False ignores it and fetches again (malformed or too old values)

    Returns:
        The cached or fetched value

    Raises:
        ConnectionError: A cached failure, or a fetch failure when error_ttl is set
        Exception: Whatever fetch raises, when error_ttl is None
    """
    cached = cache_get(key)
    error = _cached_error(cached)
    if error is not None:
        raise ConnectionError(error)
    if cached is not None and (use is None or use(cached)):
        return cached

    try:
        value = fetch()
    except (ConnectionError, ValueError) as e:
        if error_ttl is None:
            raise
        cache_set(key, error_ttl, {"error": str(e)})
        raise ConnectionError(str(e)) from e
    cache_set(key, ttl, value)
    return value

"""Request limiters shared by every process of the app (Flask, Celery worker, background threads) through Redis.

Each limiter hands out one request slot per `min_interval` seconds. A request waits for its slot instead of
failing. Requests of user actions (Compare, predictions, matches) reserve the next free slot right away, so they
form a queue. Background requests (cache syncs) only take a slot that is free now, so they always let user
requests go first. An optional daily budget counts every request of the day (UTC); when it is used up, background
requests stop with DailyLimitReached and user requests still go through.

When Redis cannot be reached the limiter lets requests through without waiting (logged once), so the app keeps
working; the retry on HTTP 429/403 in backend.opendota stays as the safety net.
"""

from __future__ import annotations

import math
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Optional

import redis

from backend.config import Config
from backend.logging_config import setup_logging

logger = setup_logging(__name__)

LOCK_TTL_MS = 2000  # A crashed process never holds the limiter lock longer than this
LOCK_POLL_SECONDS = 0.01  # Pause between attempts to take the lock
REPORT_MIN_WAIT = 3  # Waits shorter than this (the normal pace) are not reported to on_wait
DAY_KEY_TTL = 2 * 86400  # Daily counters expire the day after

WaitCallback = Callable[[int], None]


class DailyLimitReached(Exception):
    """The daily request budget is used up; background requests stop until the next day (UTC)."""


class RateLimiter:
    """One request slot per `min_interval` seconds across all processes, with an optional daily budget.

    Attributes:
        name: Redis key prefix, e.g. "opendota"
        min_interval: Seconds between two requests
        daily_limit: Requests per UTC day before background requests stop (0 = no budget)
    """

    def __init__(
        self,
        name: str,
        min_interval: float,
        daily_limit: int = 0,
        client: Optional[Any] = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.name = name
        self.min_interval = min_interval
        self.daily_limit = daily_limit
        self._client = client
        self._clock = clock
        self._sleep = sleep
        self._redis_warned = False

    @property
    def client(self) -> Any:
        """Redis client, created on first use."""
        if self._client is None:
            self._client = redis.Redis(host=Config.REDIS_HOST, port=Config.REDIS_PORT, db=1)
        return self._client

    def _key(self, suffix: str) -> str:
        return f"ratelimit:{self.name}:{suffix}"

    def _day_key(self, now: float) -> str:
        return self._key(f"day:{datetime.fromtimestamp(now, UTC).strftime('%Y-%m-%d')}")

    def _lock(self) -> str:
        """Take the limiter lock (waits while another process holds it) and return its token."""
        token = uuid.uuid4().hex
        while not self.client.set(self._key("lock"), token, nx=True, px=LOCK_TTL_MS):
            self._sleep(LOCK_POLL_SECONDS)
        return token

    def _unlock(self, token: str) -> None:
        key = self._key("lock")
        held = self.client.get(key)
        if held is not None and (held.decode() if isinstance(held, bytes) else held) == token:
            self.client.delete(key)

    def _try_take(self, background: bool) -> tuple[float, bool]:
        """Reserve a slot when allowed.

        Returns:
            Seconds to wait, and whether a slot was reserved (False: a background request must ask again after the
            wait, because user requests hold the next slots)

        Raises:
            DailyLimitReached: For a background request when the daily budget is used up
        """
        token = self._lock()
        try:
            now = self._clock()
            next_free = float(self.client.get(self._key("next")) or 0)
            day_key = self._day_key(now)
            if background and self.daily_limit and int(self.client.get(day_key) or 0) >= self.daily_limit:
                raise DailyLimitReached(f"{self.name} daily limit of {self.daily_limit} requests reached")
            if background and next_free > now:
                return next_free - now, False
            slot = max(now, next_free)
            self.client.set(self._key("next"), repr(slot + self.min_interval), ex=max(60, math.ceil(slot - now) + 60))
            self.client.incr(day_key)
            self.client.expire(day_key, DAY_KEY_TTL)
            return slot - now, True
        finally:
            self._unlock(token)

    def acquire(self, background: bool = False, on_wait: Optional[WaitCallback] = None) -> None:
        """Wait until this process may send one request.

        Args:
            background: True for cache syncs, which go after every waiting user request and stop at the daily budget
            on_wait: Called with the wait in whole seconds when a wait is longer than the normal pace

        Raises:
            DailyLimitReached: For a background request when the daily budget is used up
        """
        while True:
            try:
                wait, reserved = self._try_take(background)
            except redis.RedisError as exc:
                if not self._redis_warned:
                    logger.warning(f"Redis unavailable, {self.name} requests are not paced: {exc}")
                    self._redis_warned = True
                return
            if wait > 0:
                if on_wait is not None and wait >= REPORT_MIN_WAIT:
                    on_wait(math.ceil(wait))
                self._sleep(wait)
            if reserved:
                return

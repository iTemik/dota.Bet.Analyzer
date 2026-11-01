"""Request limiters shared by every process of the app (Flask, Celery worker, background threads) through Redis.

Each limiter allows at most `limit` requests in any `window` seconds (a sliding window). Requests go out at once,
even in a burst, until the window is full; only then does a request wait, until the oldest request in the window
is `window` seconds old. Requests of user actions (Compare, predictions, matches) reserve the next free slot right
away, so they form a queue. Background requests (cache syncs) only take a slot that is free now and never one while
a user request is queued, so they always let user requests go first. An optional daily budget counts every
request of the day (UTC); when it is used up, background requests stop with DailyLimitReached and user requests
still go through.

When Redis cannot be reached the limiter lets requests through without waiting (logged once), so the app keeps
working; the retry on HTTP 429/403 in backend.opendota stays as the safety net.
"""

from __future__ import annotations

import json
import math
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Optional

import redis

from backend import cache
from backend.logging_config import setup_logging

logger = setup_logging(__name__)

LOCK_TTL_MS = 2000  # A crashed process never holds the limiter lock longer than this
LOCK_POLL_SECONDS = 0.01  # Pause between attempts to take the lock
REPORT_MIN_WAIT = 3  # Waits shorter than this are not reported to on_wait
DAY_KEY_TTL = 2 * 86400  # Daily counters expire the day after

WaitCallback = Callable[[int], None]

# Reports long waits of requests that pass no on_wait of their own (a cache job shows them in its status)
_wait_reporter: ContextVar[Optional[WaitCallback]] = ContextVar("wait_reporter", default=None)


@contextmanager
def report_waits(callback: WaitCallback) -> Iterator[None]:
    """Report the long waits of every request made inside this block that passes no on_wait of its own.

    Args:
        callback: Called with the wait in whole seconds
    """
    token = _wait_reporter.set(callback)
    try:
        yield
    finally:
        _wait_reporter.reset(token)


def wait_reporter() -> Optional[WaitCallback]:
    """The callback set by report_waits for the current code, or None."""
    return _wait_reporter.get()


class DailyLimitReached(Exception):
    """The daily request budget is used up; background requests stop until the next day (UTC)."""


class RateLimiter:
    """At most `limit` requests in any `window` seconds across all processes, with an optional daily budget.

    Attributes:
        name: Redis key prefix, e.g. "opendota"
        limit: Requests allowed in one window
        window: Window length in seconds
        daily_limit: Requests per UTC day before background requests stop (0 = no budget)
    """

    def __init__(
        self,
        name: str,
        limit: int,
        window: float,
        daily_limit: int = 0,
        client: Optional[Any] = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.name = name
        self.limit = limit
        self.window = window
        self.daily_limit = daily_limit
        self._client = client
        self._clock = clock
        self._sleep = sleep
        self._redis_warned = False

    @property
    def client(self) -> Any:
        """Redis client: the one given to the constructor, else the app's shared client (backend.cache)."""
        return self._client if self._client is not None else cache.redis_client

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
            day_key = self._day_key(now)
            if background and self.daily_limit and int(self.client.get(day_key) or 0) >= self.daily_limit:
                raise DailyLimitReached(f"{self.name} daily limit of {self.daily_limit} requests reached")
            # Granted request times in the last window, oldest first (user reservations can lie in the future)
            raw = self.client.get(self._key("slots"))
            slots = [t for t in json.loads(raw) if t > now - self.window] if raw else []
            slot = now if len(slots) < self.limit else max(now, slots[-self.limit] + self.window)
            if background and slots and slots[-1] > now:
                return slots[-1] - now, False  # a user request is queued: let it go first
            if background and slot > now:
                return slot - now, False
            slots.append(slot)
            self.client.set(
                self._key("slots"), json.dumps(slots[-self.limit :]), ex=math.ceil(slot - now + self.window) + 1
            )
            self.client.incr(day_key)
            self.client.expire(day_key, DAY_KEY_TTL)
            return slot - now, True
        finally:
            self._unlock(token)

    def used_today(self) -> Optional[int]:
        """Requests counted today (UTC) by every process, or None when Redis cannot be reached."""
        try:
            return int(self.client.get(self._day_key(self._clock())) or 0)
        except redis.RedisError as exc:
            logger.warning(f"Could not read today's {self.name} request count: {exc}")
            return None

    def acquire(self, background: bool = False, on_wait: Optional[WaitCallback] = None) -> None:
        """Wait until this process may send one request.

        Args:
            background: True for cache syncs, which go after every waiting user request and stop at the daily budget
            on_wait: Called with the wait in whole seconds when a wait is 3 s or longer (defaults to
                the report_waits callback)

        Raises:
            DailyLimitReached: For a background request when the daily budget is used up
        """
        on_wait = on_wait or wait_reporter()
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

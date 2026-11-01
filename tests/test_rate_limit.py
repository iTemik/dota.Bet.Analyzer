"""Tests for the shared request limiter (backend.rate_limit), with an in-memory Redis and a fake clock."""

from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest
import redis

from backend.rate_limit import DailyLimitReached, RateLimiter, report_waits

START = 1_793_000_000.0  # 2026-10-26 (UTC), far from midnight


class FakeRedis:
    """The few Redis commands the limiter uses."""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    def get(self, key: str) -> Optional[bytes]:
        value = self.data.get(key)
        return None if value is None else str(value).encode()

    def set(self, key: str, value: Any, nx: bool = False, px: Optional[int] = None, ex: Optional[int] = None):
        if nx and key in self.data:
            return None
        self.data[key] = value
        return True

    def delete(self, key: str) -> None:
        self.data.pop(key, None)

    def incr(self, key: str) -> int:
        count = int(self.data.get(key, 0)) + 1
        self.data[key] = count
        return count

    def expire(self, key: str, ttl: int) -> None:
        pass


class Clock:
    """Fake time: sleeping moves the clock."""

    def __init__(self) -> None:
        self.now = START
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 3))
        self.now += seconds


@pytest.fixture
def clock() -> Clock:
    return Clock()


def limiter(clock: Clock, client: Optional[FakeRedis] = None, daily_limit: int = 0) -> RateLimiter:
    return RateLimiter(
        "test", 1.2, daily_limit=daily_limit, client=client or FakeRedis(), clock=clock.time, sleep=clock.sleep
    )


def test_requests_are_paced(clock):
    lim = limiter(clock)
    for _ in range(3):
        lim.acquire()
    assert clock.sleeps == [1.2, 1.2]


def test_no_wait_after_a_pause(clock):
    lim = limiter(clock)
    lim.acquire()
    clock.now += 5
    lim.acquire()
    assert clock.sleeps == []


def test_processes_share_one_pace(clock):
    """Two limiters on the same Redis (e.g. Flask and the Celery worker) queue behind each other."""
    shared = FakeRedis()
    limiter(clock, shared).acquire()
    limiter(clock, shared).acquire()
    assert clock.sleeps == [1.2]


def test_user_requests_go_before_background(clock):
    shared = FakeRedis()
    user = limiter(clock, shared)
    background = limiter(clock, shared)
    user.acquire()
    user.acquire()  # reserves the slot at +1.2 and waits for it
    clock.now = START  # a background request arrives while user slots are taken up to +2.4
    background.acquire(background=True)
    assert clock.sleeps == [1.2, 2.4]  # it waits until every reserved user slot has passed
    assert clock.now == pytest.approx(START + 2.4)


def test_long_waits_are_reported(clock):
    shared = FakeRedis()
    shared.data["ratelimit:test:next"] = START + 10
    waits: list[int] = []
    limiter(clock, shared).acquire(on_wait=waits.append)
    limiter(clock, shared).acquire(on_wait=waits.append)  # normal pace, not reported
    assert waits == [10]


def test_daily_limit_stops_background_but_not_user_requests(clock):
    lim = limiter(clock, daily_limit=2)
    lim.acquire(background=True)
    lim.acquire()
    with pytest.raises(DailyLimitReached):
        lim.acquire(background=True)
    lim.acquire()  # Compare still works
    assert lim.client.data["ratelimit:test:day:2026-10-26"] == 3


def test_budget_starts_again_next_day(clock):
    lim = limiter(clock, daily_limit=1)
    lim.acquire(background=True)
    clock.now += 86400
    lim.acquire(background=True)


def test_lock_held_by_another_process_is_waited_for(clock):
    shared = FakeRedis()
    shared.data["ratelimit:test:lock"] = "other"
    lim = limiter(clock, shared)
    original_sleep = clock.sleep

    def release_lock(seconds: float) -> None:
        original_sleep(seconds)
        shared.delete("ratelimit:test:lock")

    lim._sleep = release_lock
    lim.acquire()
    assert clock.sleeps == [0.01]
    assert "ratelimit:test:lock" not in shared.data


def test_redis_down_lets_requests_through(clock):
    client = MagicMock()
    client.set.side_effect = redis.ConnectionError("down")
    lim = limiter(clock, client)
    lim.acquire()
    lim.acquire()
    assert clock.sleeps == []


def test_liquipedia_fetch_waits_for_its_limiter():
    from backend.matches import LIQUIPEDIA_LIMITER, fetch_matches_from_liquipedia

    assert LIQUIPEDIA_LIMITER.min_interval == 30
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"parse": {"text": ""}}
    with (
        patch.object(LIQUIPEDIA_LIMITER, "acquire") as acquire,
        patch("backend.matches.requests.get", return_value=resp),
    ):
        assert fetch_matches_from_liquipedia() == []
    acquire.assert_called_once_with(background=False)


def test_used_today_counts_every_request_of_the_day(clock):
    lim = limiter(clock, daily_limit=5)
    assert lim.used_today() == 0
    lim.acquire()
    lim.acquire(background=True)
    assert lim.used_today() == 2
    clock.now += 86400
    assert lim.used_today() == 0


def test_used_today_is_none_when_redis_is_down(clock):
    client = MagicMock()
    client.get.side_effect = redis.ConnectionError("down")
    assert limiter(clock, client).used_today() is None


def test_report_waits_is_the_default_on_wait(clock):
    shared = FakeRedis()
    shared.data["ratelimit:test:next"] = START + 10
    waits: list[int] = []
    with report_waits(waits.append):
        limiter(clock, shared).acquire()
    limiter(clock, shared).acquire()  # outside the block: nothing reported
    assert waits == [10]

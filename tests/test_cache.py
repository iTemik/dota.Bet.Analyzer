"""Tests for the shared Redis client and the cached_json helper."""

import json
from unittest.mock import MagicMock, patch

import pytest

from backend import cache
from backend.cache import cache_get, cached_json


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str):
        return self.store.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value.encode()
        self.ttls[key] = ttl


@pytest.fixture
def fake_redis():
    redis = FakeRedis()
    with patch.object(cache, "redis_client", redis):
        yield redis


def test_miss_fetches_and_caches_then_hit_skips_fetch(fake_redis):
    fetch = MagicMock(return_value={"a": 1})
    assert cached_json("k", 100, fetch) == {"a": 1}
    assert cached_json("k", 100, fetch) == {"a": 1}
    assert fetch.call_count == 1
    assert fake_redis.ttls["k"] == 100


def test_use_false_fetches_again(fake_redis):
    fake_redis.store["k"] = json.dumps({"old": True}).encode()
    assert cached_json("k", 100, lambda: {"new": True}, use=lambda value: "new" in value) == {"new": True}
    assert json.loads(fake_redis.store["k"]) == {"new": True}


def test_error_is_cached_and_raised_again(fake_redis):
    with pytest.raises(ConnectionError, match="down"):
        cached_json("k", 100, MagicMock(side_effect=ValueError("down")), error_ttl=60)
    assert fake_redis.ttls["k"] == 60
    fetch = MagicMock(return_value=[1])
    with pytest.raises(ConnectionError, match="down"):
        cached_json("k", 100, fetch, error_ttl=60)
    fetch.assert_not_called()


def test_error_without_error_ttl_is_not_cached(fake_redis):
    with pytest.raises(ValueError):
        cached_json("k", 100, MagicMock(side_effect=ValueError("bad")))
    assert "k" not in fake_redis.store


def test_redis_down_fetches_every_time():
    broken = MagicMock()
    broken.get.side_effect = ConnectionError("no redis")
    broken.setex.side_effect = ConnectionError("no redis")
    fetch = MagicMock(return_value=[1])
    with patch.object(cache, "redis_client", broken):
        assert cached_json("k", 100, fetch) == [1]
        assert cached_json("k", 100, fetch) == [1]
    assert fetch.call_count == 2


def test_invalid_json_is_a_miss(fake_redis):
    fake_redis.store["k"] = b"not json"
    assert cache_get("k") is None
    assert cached_json("k", 100, lambda: 5) == 5


def test_rate_limiter_uses_shared_client_by_default():
    from backend.rate_limit import RateLimiter

    shared = MagicMock()
    with patch.object(cache, "redis_client", shared):
        assert RateLimiter("x", 1).client is shared

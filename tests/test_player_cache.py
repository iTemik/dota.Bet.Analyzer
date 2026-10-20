"""Tests for Redis caching of player matches and ranks in the statistics task."""

import json
from unittest.mock import MagicMock, patch

from backend.stats import MatchStats

MATCH = MatchStats(match_id=1, player_slot=0, radiant_win=True, game_mode=22, lobby_type=7, hero_id=5)


def test_matches_fetched_once_then_cached():
    from backend import task_store

    store: dict[str, bytes] = {}
    redis = MagicMock()
    redis.get.side_effect = lambda key: store.get(key)
    redis.setex.side_effect = lambda key, ttl, value: store.__setitem__(key, value.encode())

    with (
        patch.object(task_store, "redis_client", redis),
        patch.object(task_store, "get_matches", return_value=[MATCH]) as fetch,
    ):
        first = task_store.get_matches_cached(42, 20)
        second = task_store.get_matches_cached(42, 20)

    assert fetch.call_count == 1
    assert first == second == [MATCH]
    assert redis.setex.call_args.args[1] == task_store.PLAYER_MATCHES_CACHE_TTL


def test_rank_none_is_cached_too():
    from backend import task_store

    redis = MagicMock()
    redis.get.return_value = json.dumps({"rank": None}).encode()

    with patch.object(task_store, "redis_client", redis), patch.object(task_store, "get_rank") as fetch:
        assert task_store.get_rank_cached(42) is None

    fetch.assert_not_called()


def test_cache_errors_fall_through_to_api():
    from backend import task_store

    redis = MagicMock()
    redis.get.side_effect = ConnectionError("redis down")
    redis.setex.side_effect = ConnectionError("redis down")

    with patch.object(task_store, "redis_client", redis), patch.object(task_store, "get_rank", return_value=7):
        assert task_store.get_rank_cached(42) == 7

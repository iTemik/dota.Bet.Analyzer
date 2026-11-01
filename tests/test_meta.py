"""Tests for the hero meta (backend.meta) and GET /api/heroes/meta."""

from unittest.mock import patch

import pytest

from backend.meta import (
    CACHE_KEY,
    CACHE_TTL,
    ERROR_CACHE_TTL,
    MIN_REFRESH_INTERVAL,
    MetaParams,
    compute_meta,
    fetch_hero_stats,
)
from backend.opendota import OpenDotaError


def hero_stats_entry(hero_id: int, name: str, pro: tuple[int, int, int], pubs: dict[int, tuple[int, int]]) -> dict:
    """One /heroStats entry: pro = (picks, wins, bans), pubs = {bracket: (picks, wins)}."""
    entry = {
        "id": hero_id,
        "name": f"npc_dota_hero_{name.lower()}",
        "localized_name": name,
        "icon": f"/apps/dota2/images/dota_react/heroes/icons/{name.lower()}.png?",
        "pro_pick": pro[0],
        "pro_win": pro[1],
        "pro_ban": pro[2],
    }
    for bracket in range(1, 9):
        picks, wins = pubs.get(bracket, (0, 0))
        entry[f"{bracket}_pick"] = picks
        entry[f"{bracket}_win"] = wins
    return entry


# 100 pro picks in total = 10 pro matches; pubs: brackets 6-8 (Ancient, Divine, Immortal) count, lower ones don't
HERO_STATS = [
    hero_stats_entry(1, "Alpha", (5, 4, 0), {7: (100, 60)}),  # P+B 50%, win 80%: ultra
    hero_stats_entry(2, "Beta", (2, 2, 2), {7: (100, 40), 8: (20, 15)}),  # P+B 40%, 2/2 wins: too few picks for ultra
    hero_stats_entry(3, "Gamma", (3, 1, 0), {7: (50, 30), 6: (10, 9)}),  # P+B exactly 30%: not meta
    hero_stats_entry(4, "Delta", (90, 50, 10), {7: (50, 26), 5: (1000, 900)}),  # P+B 1000%, win 55.6%
]


def test_fetch_hero_stats_keeps_used_fields():
    with patch("backend.meta.get_json", return_value=[*HERO_STATS, {"id": "x"}]):
        heroes = fetch_hero_stats()
    assert len(heroes) == 4  # malformed entry skipped
    assert heroes[0] == {
        "hero_id": 1,
        "localized_name": "Alpha",
        "icon": "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/icons/alpha.png",
        "pro_pick": 5,
        "pro_win": 4,
        "pro_ban": 0,
        "pub_pick": 100,
        "pub_win": 60,
    }


def test_fetch_hero_stats_errors():
    with patch("backend.meta.get_json", side_effect=OpenDotaError(503, "NETWORK_ERROR", "down")):
        with pytest.raises(ConnectionError):
            fetch_hero_stats()
    with patch("backend.meta.get_json", return_value={"not": "a list"}):
        with pytest.raises(ValueError):
            fetch_hero_stats()


def heroes():
    with patch("backend.meta.get_json", return_value=HERO_STATS):
        return fetch_hero_stats()


def test_compute_meta_defaults():
    meta = compute_meta(heroes(), MetaParams())
    assert meta["pro_matches"] == 10
    assert [h["localized_name"] for h in meta["pro_meta"]] == ["Delta", "Alpha", "Beta"]
    assert meta["pro_meta"][1] == {
        "hero_id": 1,
        "localized_name": "Alpha",
        "icon": "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/icons/alpha.png",
        "picks": 5,
        "bans": 0,
        "wins": 4,
        "pick_ban_rate": 50.0,
        "win_rate": 80.0,
    }
    assert [h["localized_name"] for h in meta["ultra_meta"]] == ["Alpha", "Delta"]
    # Immortal + Divine + Ancient together (Legend games of Delta are left out), most picked first, win rate above 52%:
    # Beta (120 picks) has 45.8% and Delta exactly 52%
    assert meta["pub_matches"] == 33
    assert [(h["localized_name"], h["picks"], h["win_rate"]) for h in meta["pub_meta"]] == [
        ("Alpha", 100, 60.0),
        ("Gamma", 60, 65.0),
    ]
    assert meta["pub_meta"][0]["pick_rate"] == pytest.approx(303.0)


def test_compute_meta_custom_params():
    params = MetaParams(pro_min_pick_ban=20, ultra_min_win=50, ultra_min_picks=1, pub_top=2, pub_min_win=40)
    meta = compute_meta(heroes(), params)
    assert [h["localized_name"] for h in meta["pro_meta"]] == ["Delta", "Alpha", "Beta", "Gamma"]
    assert [h["localized_name"] for h in meta["ultra_meta"]] == ["Beta", "Alpha", "Delta"]
    # Only the 2 most picked count, so Gamma (65%) is left out
    assert [h["localized_name"] for h in meta["pub_meta"]] == ["Beta", "Alpha"]


def test_compute_meta_empty():
    meta = compute_meta([], MetaParams())
    assert meta["pro_matches"] == 0
    assert meta["pro_meta"] == meta["ultra_meta"] == meta["pub_meta"] == []
    assert meta["pub_matches"] == 0


class FakeRedis:
    """In-memory stand-in for the Redis client (get/setex)."""

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
    with patch("backend.meta.redis_client", redis):
        yield redis


def test_endpoint_returns_meta_and_caches(client, fake_redis):
    with patch("backend.meta.get_json", return_value=HERO_STATS) as get:
        response = client.get("/api/heroes/meta")
        again = client.get("/api/heroes/meta?pro_min_pick_ban=20&pub_top=2")
    assert get.call_count == 1  # new thresholds reuse the cached answer
    assert fake_redis.ttls[CACHE_KEY] == CACHE_TTL
    assert response.status_code == 200
    data = response.get_json()
    assert data["params"] == {
        "pro_min_pick_ban": 30.0,
        "ultra_min_win": 55.0,
        "ultra_min_picks": 5,
        "pub_top": 30,
        "pub_min_win": 52.0,
    }
    assert [h["hero_id"] for h in data["pro_meta"]] == [4, 1, 2]
    assert data["pub_matches"] == 33
    assert isinstance(data["fetched_at"], int)
    again_data = again.get_json()
    assert [h["hero_id"] for h in again_data["pro_meta"]] == [4, 1, 2, 3]
    assert [h["hero_id"] for h in again_data["pub_meta"]] == [1]  # of Beta and Alpha, only Alpha is above 52%


def test_endpoint_rejects_invalid_params(client, fake_redis):
    for query in (
        "pro_min_pick_ban=101",
        "pro_min_pick_ban=-1",
        "pub_top=0",
        "ultra_min_picks=0",
        "ultra_min_win=abc",
        "pub_min_win=101",
    ):
        assert client.get(f"/api/heroes/meta?{query}").status_code == 422, query


def test_endpoint_error_returns_503_and_is_cached(client, fake_redis):
    with patch("backend.meta.get_json", side_effect=OpenDotaError(429, "HTTP_ERROR", "HTTP 429")):
        response = client.get("/api/heroes/meta")
    assert response.status_code == 503
    assert response.get_json()["code"] == "FAILED_TO_FETCH_HERO_STATS"
    assert fake_redis.ttls[CACHE_KEY] == ERROR_CACHE_TTL
    with patch("backend.meta.get_json", return_value=HERO_STATS) as get:
        assert client.get("/api/heroes/meta").status_code == 503
    get.assert_not_called()


def test_endpoint_works_without_redis(client):
    class Broken:
        def get(self, key):
            raise ConnectionError("no redis")

        def setex(self, *args):
            raise ConnectionError("no redis")

    with patch("backend.meta.redis_client", Broken()), patch("backend.meta.get_json", return_value=HERO_STATS):
        response = client.get("/api/heroes/meta")
    assert response.status_code == 200


def test_endpoint_refresh_fetches_again_at_most_once_a_minute(client, fake_redis):
    with patch("backend.meta.get_json", return_value=HERO_STATS) as get, patch("backend.meta.time.time") as now:
        now.return_value = 1_000_000
        client.get("/api/heroes/meta")
        assert client.get("/api/heroes/meta?refresh=true").status_code == 200
        assert get.call_count == 1  # cached stats are newer than MIN_REFRESH_INTERVAL
        now.return_value = 1_000_000 + MIN_REFRESH_INTERVAL
        response = client.get("/api/heroes/meta?refresh=true")
        assert get.call_count == 2
    assert response.get_json()["fetched_at"] == 1_000_000 + MIN_REFRESH_INTERVAL
    assert "refresh" not in response.get_json()["params"]

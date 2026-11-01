"""Current hero meta from OpenDota /heroStats, for the Meta tab.

One /heroStats request returns, per hero, the pro picks, wins and bans and the pub picks and wins per rank
bracket, all over OpenDota's own recent window (about the last 7 days). The answer is cached in Redis for
CACHE_TTL, so the thresholds (query parameters) can be changed without a new request.

- Pro meta: heroes whose pick + ban rate in pro matches is above `pro_min_pick_ban` percent. The rate is
  (picks + bans) / pro matches, where pro matches = all pro picks / 10, the same as OpenDota's Pro P+B%.
- Ultra meta: pro meta heroes with a pro win rate above `ultra_min_win` percent and at least `ultra_min_picks` picks.
- Pub meta: of the `pub_top` most picked heroes in Immortal, Divine and Ancient games together (OpenDota's
  "Imm/Div/Anc" columns on its public heroes page), those with a win rate above `pub_min_win` percent.
"""

import json
import time
from dataclasses import dataclass
from typing import Any, Optional

from backend.heroes import HERO_IMAGE_HOST
from backend.logging_config import setup_logging
from backend.opendota import OpenDotaError, get_json
from backend.task_store import redis_client

logger = setup_logging(__name__)

CACHE_KEY = "opendota:hero_stats:v2"  # v2: pub picks and wins summed over PUB_BRACKETS
CACHE_TTL = 3600  # seconds; OpenDota recomputes hero stats a few times a day
ERROR_CACHE_TTL = 60  # a failed request is not repeated sooner
MIN_REFRESH_INTERVAL = 60  # seconds; a forced refresh of newer stats uses the cache

PUB_BRACKETS = (6, 7, 8)  # Ancient, Divine, Immortal: OpenDota's "Imm/Div/Anc"
PICKS_PER_MATCH = 10


@dataclass(frozen=True)
class MetaParams:
    """Meta thresholds; every field is a query parameter of GET /api/heroes/meta."""

    pro_min_pick_ban: float = 30.0  # percent of pro matches
    ultra_min_win: float = 55.0  # percent
    ultra_min_picks: int = 5  # so a hero with 2 wins in 2 picks is not ultra meta
    pub_top: int = 30  # most picked heroes
    pub_min_win: float = 52.0  # percent


def _hero_stat(entry: dict[str, Any]) -> dict[str, Any]:
    """Fields of one /heroStats entry used by the meta lists."""
    icon = entry.get("icon") or ""
    return {
        "hero_id": int(entry["id"]),
        "localized_name": str(entry["localized_name"]),
        "icon": f"{HERO_IMAGE_HOST}{icon.rstrip('?')}" if icon.startswith("/") else icon,
        "pro_pick": int(entry.get("pro_pick") or 0),
        "pro_win": int(entry.get("pro_win") or 0),
        "pro_ban": int(entry.get("pro_ban") or 0),
        "pub_pick": sum(int(entry.get(f"{b}_pick") or 0) for b in PUB_BRACKETS),
        "pub_win": sum(int(entry.get(f"{b}_win") or 0) for b in PUB_BRACKETS),
    }


def fetch_hero_stats() -> list[dict[str, Any]]:
    """Fetch /heroStats from OpenDota and keep only the fields used here.

    Returns:
        One entry per hero: hero_id, localized_name, icon, pro_pick, pro_win, pro_ban, pub_pick, pub_win

    Raises:
        ConnectionError: If OpenDota could not be reached or answered with an error
        ValueError: If the answer is not a list of hero entries
    """
    try:
        data = get_json("/heroStats", timeout=30)
    except OpenDotaError as e:
        if e.code == "JSON_DECODE_ERROR":
            raise ValueError(f"Unexpected heroStats response: {e}") from e
        raise ConnectionError(f"Failed to fetch hero stats from OpenDota API: {e}") from e
    if not isinstance(data, list):
        raise ValueError(f"Expected list from heroStats, got {type(data).__name__}")

    heroes = []
    for entry in data:
        try:
            heroes.append(_hero_stat(entry))
        except (AttributeError, KeyError, TypeError, ValueError):
            logger.warning(f"Skipping malformed heroStats entry: {entry!r}")
    return heroes


def _cache_put(data: dict[str, Any], ttl: int) -> None:
    try:
        redis_client.setex(CACHE_KEY, ttl, json.dumps(data))
    except Exception as e:
        logger.warning(f"Failed to cache hero stats: {e}")


def cached_hero_stats(refresh: bool = False) -> tuple[list[dict[str, Any]], int]:
    """Hero stats from Redis, fetched from OpenDota when the cache is empty.

    A failure is cached for ERROR_CACHE_TTL and raised again from the cache.

    Args:
        refresh: Fetch again even when cached, unless the cached stats are newer than MIN_REFRESH_INTERVAL

    Returns:
        Hero stats as returned by fetch_hero_stats, and the fetch time (unix seconds)

    Raises:
        ConnectionError: If OpenDota could not be reached or its answer was invalid
    """
    try:
        cached = redis_client.get(CACHE_KEY)
    except Exception as e:
        logger.warning(f"Redis unavailable for hero stats cache: {e}")
        cached = None
    if cached is not None:
        data: dict[str, Any] = json.loads(cached)
        if "error" in data:
            raise ConnectionError(data["error"])
        if not refresh or time.time() - int(data["fetched_at"]) < MIN_REFRESH_INTERVAL:
            return data["heroes"], int(data["fetched_at"])

    try:
        heroes = fetch_hero_stats()
    except (ConnectionError, ValueError) as e:
        _cache_put({"error": str(e)}, ERROR_CACHE_TTL)
        raise ConnectionError(str(e)) from e
    fetched_at = int(time.time())
    _cache_put({"heroes": heroes, "fetched_at": fetched_at}, CACHE_TTL)
    return heroes, fetched_at


def _percent(part: int, whole: int) -> Optional[float]:
    return round(100 * part / whole, 1) if whole else None


def compute_meta(heroes: list[dict[str, Any]], params: MetaParams) -> dict[str, Any]:
    """Pro, ultra and pub meta lists from cached hero stats.

    Args:
        heroes: Hero stats as returned by fetch_hero_stats
        params: Thresholds

    Returns:
        pro_matches, pub_matches, and the lists pro_meta (pick + ban rate,
        highest first), ultra_meta (subset of pro_meta, highest win rate first) and pub_meta (most picked first)
    """
    pro_matches = round(sum(h["pro_pick"] for h in heroes) / PICKS_PER_MATCH)

    pro_meta = []
    for h in heroes:
        pick_ban_rate = _percent(h["pro_pick"] + h["pro_ban"], pro_matches)
        if pick_ban_rate is None or pick_ban_rate <= params.pro_min_pick_ban:
            continue
        pro_meta.append(
            {
                "hero_id": h["hero_id"],
                "localized_name": h["localized_name"],
                "icon": h["icon"],
                "picks": h["pro_pick"],
                "bans": h["pro_ban"],
                "wins": h["pro_win"],
                "pick_ban_rate": pick_ban_rate,
                "win_rate": _percent(h["pro_win"], h["pro_pick"]),
            }
        )
    pro_meta.sort(key=lambda h: (-h["pick_ban_rate"], h["localized_name"]))

    ultra_meta = [
        h
        for h in pro_meta
        if h["picks"] >= params.ultra_min_picks and h["win_rate"] is not None and h["win_rate"] > params.ultra_min_win
    ]
    ultra_meta = sorted(ultra_meta, key=lambda h: (-h["win_rate"], h["localized_name"]))

    pub_matches = round(sum(h["pub_pick"] for h in heroes) / PICKS_PER_MATCH)
    pub = [
        {
            "hero_id": h["hero_id"],
            "localized_name": h["localized_name"],
            "icon": h["icon"],
            "picks": h["pub_pick"],
            "wins": h["pub_win"],
            "pick_rate": _percent(h["pub_pick"], pub_matches),
            "win_rate": _percent(h["pub_win"], h["pub_pick"]),
        }
        for h in heroes
        if h["pub_pick"]
    ]
    pub.sort(key=lambda h: (-h["picks"], h["localized_name"]))
    pub = [h for h in pub[: params.pub_top] if h["win_rate"] > params.pub_min_win]

    return {
        "pro_matches": pro_matches,
        "pub_matches": pub_matches,
        "pro_meta": pro_meta,
        "ultra_meta": ultra_meta,
        "pub_meta": pub,
    }


def get_meta(params: MetaParams, refresh: bool = False) -> dict[str, Any]:
    """Meta lists for GET /api/heroes/meta: at most one /heroStats request per CACHE_TTL.

    Args:
        params: Thresholds
        refresh: Fetch the hero stats again instead of using the cache (see cached_hero_stats)

    Returns:
        compute_meta output plus fetched_at (when the hero stats were fetched) and the params used

    Raises:
        ConnectionError: If the hero stats could not be fetched
    """
    heroes, fetched_at = cached_hero_stats(refresh)
    return {"fetched_at": fetched_at, "params": params.__dict__, **compute_meta(heroes, params)}

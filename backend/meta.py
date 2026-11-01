"""Current hero meta from OpenDota /heroStats, for the Meta tab.

One /heroStats request returns, per hero, the pro picks, wins and bans and the pub picks and wins per rank
bracket, all over OpenDota's own recent window (about the last 7 days). The answer is cached in Redis for
CACHE_TTL, so the thresholds (query parameters) can be changed without a new request. The `hero_meta` cache job
(backend.jobs) refreshes it every hour, so a page load rarely waits for OpenDota.

- Pro meta: heroes whose pick + ban rate in pro matches is above `pro_min_pick_ban` percent. The rate is
  (picks + bans) / pro matches, where pro matches = all pro picks / 10, the same as OpenDota's Pro P+B%.
- Ultra meta: pro meta heroes with a pro win rate above `ultra_min_win` percent and at least `ultra_min_picks` picks.
- Pub meta: of the `pub_top` most picked heroes in Immortal, Divine and Ancient games together (OpenDota's
  "Imm/Div/Anc" columns on its public heroes page), those with a win rate above `pub_min_win` percent.
"""

import time
from dataclasses import dataclass
from typing import Any, Optional

from backend.cache import cache_set, cached_json
from backend.heroes import HERO_IMAGE_HOST
from backend.logging_config import setup_logging
from backend.opendota import OpenDotaError, get_json

logger = setup_logging(__name__)

CACHE_KEY = "opendota:hero_stats:v2"  # v2: pub picks and wins summed over PUB_BRACKETS
CACHE_TTL = 2 * 3600  # seconds; longer than the hourly hero_meta job, so the job refreshes it before it expires
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


def fetch_hero_stats(background: bool = False) -> list[dict[str, Any]]:
    """Fetch /heroStats from OpenDota and keep only the fields used here.

    Args:
        background: True for the cache job: lets user requests go first and stops at the daily budget

    Returns:
        One entry per hero: hero_id, localized_name, icon, pro_pick, pro_win, pro_ban, pub_pick, pub_win

    Raises:
        ConnectionError: If OpenDota could not be reached or answered with an error
        ValueError: If the answer is not a list of hero entries
    """
    try:
        data = get_json("/heroStats", timeout=30, background=background)
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


def _fetch_entry(background: bool = False) -> dict[str, Any]:
    """Cache entry for fetched hero stats: {"heroes": [...], "fetched_at": unix seconds}."""
    return {"heroes": fetch_hero_stats(background), "fetched_at": int(time.time())}


def refresh_hero_stats(background: bool = False) -> tuple[list[dict[str, Any]], int]:
    """Fetch the hero stats and cache them for CACHE_TTL.

    Args:
        background: True for the cache job (see fetch_hero_stats)

    Returns:
        Hero stats as returned by fetch_hero_stats, and the fetch time (unix seconds)

    Raises:
        ConnectionError, ValueError: As fetch_hero_stats
        DailyLimitReached: For a background fetch when the daily budget is used up
    """
    data = _fetch_entry(background)
    cache_set(CACHE_KEY, CACHE_TTL, data)
    return data["heroes"], data["fetched_at"]


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
    data = cached_json(
        CACHE_KEY,
        CACHE_TTL,
        _fetch_entry,
        error_ttl=ERROR_CACHE_TTL,
        use=lambda cached: not refresh or time.time() - int(cached["fetched_at"]) < MIN_REFRESH_INTERVAL,
    )
    return data["heroes"], int(data["fetched_at"])


def _percent(part: int, whole: int) -> Optional[float]:
    return round(100 * part / whole, 1) if whole else None


def compute_meta(heroes: list[dict[str, Any]], params: MetaParams) -> dict[str, Any]:
    """Pro, ultra and pub meta heroes from cached hero stats, in one list.

    Args:
        heroes: Hero stats as returned by fetch_hero_stats
        params: Thresholds

    Returns:
        pro_matches, pub_matches and `heroes`: every hero in at least one meta, with its pro and pub stats and
        `meta` (the metas it is in, of "ultra", "pro" and "pub"); ultra first, then pro, then pub only, each
        by pro pick + ban rate and then pub picks
    """
    pro_matches = round(sum(h["pro_pick"] for h in heroes) / PICKS_PER_MATCH)
    pub_matches = round(sum(h["pub_pick"] for h in heroes) / PICKS_PER_MATCH)

    # Pub meta: of the pub_top most picked heroes, those above the win rate
    most_picked = sorted((h for h in heroes if h["pub_pick"]), key=lambda h: (-h["pub_pick"], h["localized_name"]))
    pub_ids = {
        h["hero_id"]
        for h in most_picked[: params.pub_top]
        if (_percent(h["pub_win"], h["pub_pick"]) or 0) > params.pub_min_win
    }

    result = []
    for h in heroes:
        pick_ban_rate = _percent(h["pro_pick"] + h["pro_ban"], pro_matches)
        pro_win_rate = _percent(h["pro_win"], h["pro_pick"])
        meta = []
        if pick_ban_rate is not None and pick_ban_rate > params.pro_min_pick_ban:
            if (
                h["pro_pick"] >= params.ultra_min_picks
                and pro_win_rate is not None
                and pro_win_rate > params.ultra_min_win
            ):
                meta.append("ultra")
            meta.append("pro")
        if h["hero_id"] in pub_ids:
            meta.append("pub")
        if not meta:
            continue
        result.append(
            {
                "hero_id": h["hero_id"],
                "localized_name": h["localized_name"],
                "icon": h["icon"],
                "meta": meta,
                "pro_picks": h["pro_pick"],
                "pro_bans": h["pro_ban"],
                "pro_wins": h["pro_win"],
                "pro_pick_ban_rate": pick_ban_rate,
                "pro_win_rate": pro_win_rate,
                "pub_picks": h["pub_pick"],
                "pub_wins": h["pub_win"],
                "pub_pick_rate": _percent(h["pub_pick"], pub_matches),
                "pub_win_rate": _percent(h["pub_win"], h["pub_pick"]),
            }
        )
    rank = {"ultra": 0, "pro": 1, "pub": 2}
    result.sort(
        key=lambda h: (rank[h["meta"][0]], -(h["pro_pick_ban_rate"] or 0), -h["pub_picks"], h["localized_name"])
    )
    return {"pro_matches": pro_matches, "pub_matches": pub_matches, "heroes": result}


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

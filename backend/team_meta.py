"""Does a team play the current meta heroes? Meta state and picked meta heroes for Team Insights.

Two parts, so the per-player requests run in the Celery task and not in the /statistics request:

1. `load_team_games` (in the /statistics request, from compute_statistics): the team's league games of the deeper
   window with every pick of the team's side. Team matches and lineups are cached in SQLite, so after the first
   time this costs 0 requests (1-3 explorer requests the first time, plus /constants/patch once a week).
2. `compute_team_meta` (in players_statistics_task): per player, the meta heroes they practise (league picks from
   1, plus `/players/{id}/heroes` for league + pub games, cached 24 h), then the team state from all of it.

Rules (defaults in TeamMetaParams, every one a query parameter of GET /api/statistics):

- Meta hero: in the pro (or ultra) meta of the Meta tab, with the thresholds of MetaParams.
- Meta game: a team game with at least `meta_min_heroes` meta heroes picked by the team (stand-ins included).
- States, first match wins: `actively` (the recent window, `days`, has `meta_min_games` games and at least
  `meta_min_games_pct` percent are meta games), `tries` (the same on the deeper window, `deep_days`), `players_know`
  (at least `players_know_min` core players practise a meta hero), `doesnt_play` (enough deeper games, but no rule
  passed), `no_info` (not enough games and no player practice).
- Practice: a player has at least `practice_league_games` league games or `practice_total_games` games of any kind
  (league + pubs, from /players/{id}/heroes) on the hero in the deeper window.
- Both windows start no earlier than the latest patch when `patch_cut` is on.
"""

import math
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Optional

from backend.cache import cached_json
from backend.logging_config import setup_logging
from backend.meta import MetaParams, compute_meta
from backend.opendota import OpenDotaError, WaitCallback, get_json, is_radiant
from backend.rosters import (
    DAY_SECONDS,
    get_match_lineups,
    get_team_league_matches,
    window_start,
)

logger = setup_logging(__name__)

STATE_ACTIVELY = "actively"  # Plays meta in the recent window
STATE_TRIES = "tries"  # Plays meta only in the deeper window
STATE_PLAYERS_KNOW = "players_know"  # The team does not, but enough core players practise meta heroes
STATE_DOESNT_PLAY = "doesnt_play"  # Enough games, no rule passed
STATE_NO_INFO = "no_info"  # Not enough games and no player practice

DEEP_MAX_GAMES = 100  # At most this many of the newest league games of the deeper window are looked up
PATCHES_KEY = "opendota:patches"
PATCHES_TTL = 7 * DAY_SECONDS
PATCHES_ERROR_TTL = 60
PLAYER_HEROES_KEY = "opendota:player_heroes:{account_id}:{days}"
PLAYER_HEROES_TTL = DAY_SECONDS
TEAM_SIZE = 5


@dataclass(frozen=True)
class TeamMetaParams:
    """Windows and thresholds of the team meta state; every field is a query parameter of GET /api/statistics."""

    deep_days: int = 60  # Deeper window; the recent window is the statistics `days`
    meta_min_games: int = 20  # Games a window needs before its result counts
    meta_min_heroes: int = 2  # Meta heroes in one team draft for a meta game
    meta_min_games_pct: float = 65.0  # Percent of meta games for "plays meta"
    practice_league_games: int = 3  # League games on a hero that prove practice
    practice_total_games: int = 5  # League + pub games on a hero that prove practice
    players_know_min: int = 3  # Core players with a practised meta hero for "players know meta"
    meta_hero_min_games: int = 3  # Team picks a meta hero needs to be listed
    patch_cut: bool = True  # Windows start no earlier than the latest patch


def _fetch_patches() -> list[dict[str, Any]]:
    """OpenDota /constants/patch as [{name, start_time}].

    Raises:
        ConnectionError: If OpenDota could not be reached or the answer is not a patch list
    """
    try:
        data = get_json("/constants/patch", timeout=30)
    except OpenDotaError as e:
        raise ConnectionError(f"Failed to fetch patches from OpenDota API: {e}") from e
    if not isinstance(data, list):
        raise ConnectionError(f"Expected list from /constants/patch, got {type(data).__name__}")
    patches = []
    for entry in data:
        try:
            start = datetime.fromisoformat(str(entry["date"]).replace("Z", "+00:00"))
            patches.append({"name": str(entry["name"]), "start_time": int(start.timestamp())})
        except (KeyError, TypeError, ValueError):
            logger.warning(f"Skipping malformed patch entry: {entry!r}")
    return patches


def latest_patch(now: int) -> Optional[dict[str, Any]]:
    """The newest patch released before `now` (cached PATCHES_TTL), None when unknown.

    Args:
        now: Current unix time

    Returns:
        {"name": "7.39", "start_time": unix seconds} or None when the patch list could not be fetched
    """
    try:
        patches = cached_json(PATCHES_KEY, PATCHES_TTL, _fetch_patches, error_ttl=PATCHES_ERROR_TTL)
    except ConnectionError as e:
        logger.warning(f"Patch list unavailable, windows are not cut at the patch: {e}")
        return None
    released = [p for p in patches if p["start_time"] <= now]
    return max(released, key=lambda p: p["start_time"], default=None)


def _team_picks(lineup: list[Any], radiant: bool) -> Optional[list[list[int]]]:
    """[[account_id, hero_id], ...] of the team's side, None unless all TEAM_SIZE heroes are known."""
    side = [p for p in sorted(lineup) if is_radiant(p.player_slot) == radiant and p.hero_id]
    if len(side) < TEAM_SIZE:
        return None
    return [[int(p.account_id or 0), int(p.hero_id)] for p in side]


def load_team_games(team_id: int, days: int, params: TeamMetaParams, now: Optional[int] = None) -> dict[str, Any]:
    """The team's league games of the deeper window with the team's picks (the input of compute_team_meta).

    Args:
        team_id: Team identifier
        days: Recent window in days (the statistics `days`)
        params: Windows and thresholds
        now: Current unix time (for tests)

    Returns:
        {"recent_start", "deep_start": unix seconds, "patch": name or None,
         "games": [{"match_id", "start_time", "picks": [[account_id, hero_id], ...]}, ...] newest first};
        games without all five picked heroes are skipped
    """
    now = now if now is not None else int(time.time())
    patch = latest_patch(now) if params.patch_cut else None
    patch_start = patch["start_time"] if patch else 0
    recent_start = max(window_start(days, now), patch_start)
    deep_start = max(window_start(max(params.deep_days, days), now), patch_start)

    matches = [m for m in get_team_league_matches(team_id, now=now) if m.start_time >= deep_start]
    matches = matches[:DEEP_MAX_GAMES]
    lineups = get_match_lineups(m.match_id for m in matches) if matches else {}
    games = []
    for match in matches:
        picks = _team_picks(lineups.get(match.match_id, []), match.radiant)
        if picks:
            games.append({"match_id": match.match_id, "start_time": match.start_time, "picks": picks})
    return {
        "recent_start": recent_start,
        "deep_start": deep_start,
        "patch": patch["name"] if patch else None,
        "games": games,
    }


def player_heroes_days(deep_start: int, now: Optional[int] = None) -> int:
    """Days to ask /players/{id}/heroes for, so it covers the deeper window (at least 1)."""
    now = now if now is not None else int(time.time())
    return max(1, math.ceil((now - deep_start) / DAY_SECONDS))


def _fetch_player_heroes(account_id: int, days: int, on_wait: Optional[WaitCallback]) -> dict[str, int]:
    """Games per hero (all game types) of a player over `days` days; heroes with 0 games are left out.

    Raises:
        OpenDotaError: If the request failed (not cached, so it is asked again next time)
    """
    data = get_json(f"/players/{int(account_id)}/heroes", params={"date": days}, on_wait=on_wait)
    games: dict[str, int] = {}
    for entry in data if isinstance(data, list) else []:
        try:
            count = int(entry.get("games") or 0)
            if count:
                games[str(int(entry["hero_id"]))] = count
        except (AttributeError, KeyError, TypeError, ValueError):
            logger.warning(f"Skipping malformed player hero entry: {entry!r}")
    return games


def get_player_heroes_cached(account_id: int, days: int, on_wait: Optional[WaitCallback] = None) -> dict[int, int]:
    """Games per hero of a player over the last `days` days (league + pubs), cached PLAYER_HEROES_TTL.

    Args:
        account_id: Player account ID
        days: Days of history
        on_wait: Called with the delay in seconds when the request waits for the OpenDota limits

    Returns:
        Games per hero id

    Raises:
        OpenDotaError: If the request failed
    """
    data = cached_json(
        PLAYER_HEROES_KEY.format(account_id=account_id, days=days),
        PLAYER_HEROES_TTL,
        lambda: _fetch_player_heroes(account_id, days, on_wait),
        use=lambda value: isinstance(value, dict),
    )
    return {int(hero_id): int(games) for hero_id, games in data.items()}


def _percent(part: int, whole: int) -> Optional[float]:
    return round(100 * part / whole, 1) if whole else None


def _window(games: list[dict[str, Any]], meta_ids: set[int], min_heroes: int) -> dict[str, Any]:
    """Games, meta games and meta pick share of a list of team games, the share of games with 2+ and 3+ meta heroes
    (shown next to each other whatever `min_heroes` is) and the number of different heroes picked."""
    picks = [hero for game in games for _, hero in game["picks"]]
    meta_counts = [sum(1 for _, hero in g["picks"] if hero in meta_ids) for g in games]
    meta_games = sum(1 for count in meta_counts if count >= min_heroes)
    return {
        "games": len(games),
        "meta_games": meta_games,
        "meta_games_pct": _percent(meta_games, len(games)),
        "meta2_games_pct": _percent(sum(1 for count in meta_counts if count >= 2), len(games)),
        "meta3_games_pct": _percent(sum(1 for count in meta_counts if count >= 3), len(games)),
        "meta_picks_pct": _percent(sum(1 for hero in picks if hero in meta_ids), len(picks)),
        "heroes": len(set(picks)),  # Different heroes the team picked (hero pool size)
    }


def _player_games(
    core: list[int],
    player_heroes: dict[int, Optional[dict[int, int]]],
    meta_ids: set[int],
    league_games: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Games of the core players (summed over players) and how many of them were on a meta hero.

    Players without hero data are left out. With `league_games`, the core players' picks in those team games are
    taken away, which leaves their pub games (and league games with other teams).

    Returns:
        {"games", "meta_games", "meta_games_pct", "players": players with hero data}
    """
    games = meta_games = players = 0
    for account_id in core:
        heroes = player_heroes.get(account_id)
        if heroes is None:
            continue
        players += 1
        counts = dict(heroes)
        for game in league_games or []:
            for player, hero in game["picks"]:
                if player == account_id and counts.get(hero, 0) > 0:
                    counts[hero] -= 1
        games += sum(counts.values())
        meta_games += sum(count for hero, count in counts.items() if hero in meta_ids)
    return {"games": games, "meta_games": meta_games, "meta_games_pct": _percent(meta_games, games), "players": players}


def _passes(window: dict[str, Any], params: TeamMetaParams) -> bool:
    return window["games"] >= params.meta_min_games and (window["meta_games_pct"] or 0) >= params.meta_min_games_pct


def _player_practice(
    games: list[dict[str, Any]],
    core: list[int],
    player_heroes: dict[int, Optional[dict[int, int]]],
    meta_ids: set[int],
    params: TeamMetaParams,
) -> list[dict[str, Any]]:
    """Per core player: the meta heroes they practise (league picks in `games` or all games from player_heroes)."""
    players = []
    for account_id in core:
        league: dict[int, int] = {}
        for game in games:
            for player, hero in game["picks"]:
                if player == account_id:
                    league[hero] = league.get(hero, 0) + 1
        total = player_heroes.get(account_id)
        practised = sorted(
            hero
            for hero in meta_ids
            if league.get(hero, 0) >= params.practice_league_games
            or (total is not None and total.get(hero, 0) >= params.practice_total_games)
        )
        players.append({"account_id": account_id, "meta_heroes": practised, "pub_known": total is not None})
    return players


def _state(recent: dict[str, Any], deep: dict[str, Any], knowers: int, params: TeamMetaParams) -> str:
    """Team meta state from both windows and the number of core players practising a meta hero."""
    if _passes(recent, params):
        return STATE_ACTIVELY
    if _passes(deep, params):
        return STATE_TRIES
    if knowers >= params.players_know_min:
        return STATE_PLAYERS_KNOW
    if deep["games"] >= params.meta_min_games:
        return STATE_DOESNT_PLAY
    return STATE_NO_INFO


def _picked_heroes(
    games: list[dict[str, Any]],
    recent_start: int,
    meta_by_id: dict[int, dict[str, Any]],
    practice_players: dict[int, int],
    min_games: int,
) -> list[dict[str, Any]]:
    """Meta heroes the team picked at least `min_games` times, with how many core players practise each; most games
    first."""
    picked: dict[int, int] = {}
    picked_recent: dict[int, int] = {}
    for game in games:
        for _, hero in game["picks"]:
            if hero in meta_by_id:
                picked[hero] = picked.get(hero, 0) + 1
                if game["start_time"] >= recent_start:
                    picked_recent[hero] = picked_recent.get(hero, 0) + 1
    heroes = [
        {
            "hero_id": hero,
            "localized_name": meta_by_id[hero]["localized_name"],
            "icon": meta_by_id[hero]["icon"],
            "ultra": "ultra" in meta_by_id[hero]["meta"],
            "games": picked.get(hero, 0),
            "recent_games": picked_recent.get(hero, 0),
            "practice_players": practice_players.get(hero, 0),
        }
        for hero, games in picked.items()
        if games >= min_games
    ]
    heroes.sort(key=lambda h: (-h["games"], -h["recent_games"], -h["practice_players"], h["localized_name"]))
    return heroes


def compute_team_meta(
    team_games: dict[str, Any],
    core: list[int],
    player_heroes: dict[int, Optional[dict[int, int]]],
    hero_stats: list[dict[str, Any]],
    meta_params: MetaParams,
    params: TeamMetaParams,
    player_heroes_recent: Optional[dict[int, Optional[dict[int, int]]]] = None,
) -> dict[str, Any]:
    """Team meta state, picked meta heroes and per-player practice.

    Args:
        team_games: load_team_games output
        core: Core player accounts (the main roster when there is no clear core)
        player_heroes: Games per hero of each core player (league + pubs, deeper window); None when unavailable
        hero_stats: Cached /heroStats (backend.meta.cached_hero_stats)
        meta_params: Meta tab thresholds
        params: Windows and thresholds
        player_heroes_recent: The same as player_heroes over the recent window; None when not fetched

    Returns:
        state, patch, recent/deep windows (games, meta_games, meta_games_pct, meta_picks_pct, start),
        pro_meta_picks_pct (share of all pro picks on meta heroes), meta_heroes_total (size of the meta list),
        heroes (meta heroes the team picked `meta_hero_min_games`+ times: hero_id, localized_name, icon, ultra, games,
        recent_games, practice_players; most games first), players (account_id, meta_heroes practised, pub_known),
        player_games (core players' games of any kind on meta heroes: recent, deep, and pub_deep without the team's
        league games; see _player_games) and the params used
    """
    meta_list = [h for h in compute_meta(hero_stats, meta_params)["heroes"] if "pro" in h["meta"]]
    meta_by_id = {h["hero_id"]: h for h in meta_list}
    meta_ids = set(meta_by_id)
    all_pro_picks = sum(h["pro_pick"] for h in hero_stats)
    pro_meta_picks = sum(h["pro_pick"] for h in hero_stats if h["hero_id"] in meta_ids)

    deep_games = team_games["games"]
    recent_games = [g for g in deep_games if g["start_time"] >= team_games["recent_start"]]
    recent = {**_window(recent_games, meta_ids, params.meta_min_heroes), "start": team_games["recent_start"]}
    deep = {**_window(deep_games, meta_ids, params.meta_min_heroes), "start": team_games["deep_start"]}

    players = _player_practice(deep_games, core, player_heroes, meta_ids, params)
    state = _state(recent, deep, sum(1 for p in players if p["meta_heroes"]), params)
    practice_players: dict[int, int] = {}
    for player in players:
        for hero in player["meta_heroes"]:
            practice_players[hero] = practice_players.get(hero, 0) + 1
    heroes = _picked_heroes(
        deep_games, team_games["recent_start"], meta_by_id, practice_players, params.meta_hero_min_games
    )

    return {
        "state": state,
        "patch": team_games.get("patch"),
        "recent": recent,
        "deep": deep,
        "pro_meta_picks_pct": _percent(pro_meta_picks, all_pro_picks),
        "meta_heroes_total": len(meta_ids),
        "heroes": heroes,
        "players": players,
        "player_games": {
            "recent": _player_games(core, player_heroes_recent or {}, meta_ids),
            "deep": _player_games(core, player_heroes, meta_ids),
            "pub_deep": _player_games(core, player_heroes, meta_ids, deep_games),
        },
        "params": asdict(params),
    }

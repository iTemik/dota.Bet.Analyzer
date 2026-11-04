"""Tests for the team meta state (backend.team_meta), its task step and how /statistics passes its settings."""

from unittest.mock import MagicMock, patch

import pytest

from backend import tasks
from backend.meta import MetaParams
from backend.models import MatchesSummary, Player, TeamStats
from backend.opendota import OpenDotaError
from backend.rosters import LineupPlayer, TeamMatch
from backend.team_meta import (
    PATCHES_KEY,
    STATE_ACTIVELY,
    STATE_DOESNT_PLAY,
    STATE_NO_INFO,
    STATE_PLAYERS_KNOW,
    STATE_TRIES,
    TeamMetaParams,
    compute_team_meta,
    get_player_heroes_cached,
    latest_patch,
    load_team_games,
    player_heroes_days,
)

NOW = 1_792_300_000
DAY = 24 * 60 * 60
CORE = [101, 102, 103, 104, 105]
META = [1, 2, 3, 4, 5]  # Pro meta heroes in HERO_STATS; hero 1 is ultra
OTHER = [6, 7, 8, 9, 10]  # Not meta


def _hero(hero_id: int, picks: int, bans: int, wins: int) -> dict:
    return {
        "hero_id": hero_id,
        "localized_name": f"Hero {hero_id}",
        "icon": f"https://cdn/hero{hero_id}.png",
        "pro_pick": picks,
        "pro_win": wins,
        "pro_ban": bans,
        "pub_pick": 0,
        "pub_win": 0,
    }


# 55 pro matches: heroes 1-5 have (100 + 50) / 55 pick + ban rate (meta), heroes 6-10 have 10 / 55 (not meta)
HERO_STATS = [_hero(1, 100, 50, 60), *[_hero(h, 100, 50, 50) for h in META[1:]], *[_hero(h, 10, 0, 5) for h in OTHER]]


def _game(match_id: int, days_ago: float, heroes: list[int], players: list[int] = CORE) -> dict:
    return {
        "match_id": match_id,
        "start_time": int(NOW - days_ago * DAY),
        "picks": [[a, h] for a, h in zip(players, heroes, strict=True)],
    }


def _games(count: int, heroes: list[int], start_days: float = 0.5, step_days: float = 0.5) -> list[dict]:
    return [_game(i, start_days + i * step_days, heroes) for i in range(count)]


def _team_games(games: list[dict], recent_days: int = 20, deep_days: int = 60) -> dict:
    return {
        "recent_start": NOW - recent_days * DAY,
        "deep_start": NOW - deep_days * DAY,
        "patch": "7.39",
        "games": games,
    }


def _meta(games: list[dict], player_heroes: dict | None = None, **params) -> dict:
    return compute_team_meta(
        _team_games(games),
        CORE,
        player_heroes if player_heroes is not None else {a: {} for a in CORE},
        HERO_STATS,
        MetaParams(),
        TeamMetaParams(**params),
    )


THREE_META = [1, 2, 3, 6, 7]  # A meta game: 3 meta heroes
TWO_META = [1, 2, 6, 7, 8]  # Not a meta game


def test_actively_plays_meta_in_recent_window():
    meta = _meta(_games(20, THREE_META))  # 20 games over the last 10 days

    assert meta["state"] == STATE_ACTIVELY
    assert meta["recent"] == {
        "games": 20,
        "meta_games": 20,
        "meta_games_pct": 100.0,
        "meta_picks_pct": 60.0,
        "start": NOW - 20 * DAY,
    }
    assert meta["pro_meta_picks_pct"] == 90.9  # 500 of 550 pro picks
    assert meta["meta_heroes_total"] == 5
    assert meta["patch"] == "7.39"
    assert meta["params"]["meta_min_games"] == 20


def test_tries_when_only_the_deeper_window_passes():
    # 10 recent games, 10 more between 25 and 34 days ago: only the 60-day window has 20 games
    games = _games(10, THREE_META) + [_game(100 + i, 25 + i, THREE_META) for i in range(10)]

    meta = _meta(games)

    assert meta["state"] == STATE_TRIES
    assert (meta["recent"]["games"], meta["deep"]["games"]) == (10, 20)


def test_meta_games_share_below_threshold_is_not_playing_meta():
    # 12 of 20 games (60%) are meta games, under 65%; practice is out of reach here
    games = _games(12, THREE_META) + [_game(100 + i, 11 + i * 0.5, TWO_META) for i in range(8)]
    meta = _meta(games, practice_league_games=100)

    assert meta["deep"]["meta_games_pct"] == 60.0
    assert meta["state"] == STATE_DOESNT_PLAY
    # A lower threshold accepts it
    assert _meta(games, meta_min_games_pct=60)["state"] == STATE_ACTIVELY
    # With the default practice rule, the league picks show 3 players practising meta heroes
    assert _meta(games)["state"] == STATE_PLAYERS_KNOW


def test_players_know_meta_from_pub_games():
    # Not enough team games, but 3 core players have 5+ games of any kind on a meta hero
    player_heroes = {101: {1: 5}, 102: {2: 9}, 103: {3: 5}, 104: {6: 30}, 105: None}

    meta = _meta(_games(3, TWO_META), player_heroes)

    assert meta["state"] == STATE_PLAYERS_KNOW
    assert meta["players"] == [
        {"account_id": 101, "meta_heroes": [1], "pub_known": True},
        {"account_id": 102, "meta_heroes": [2], "pub_known": True},
        {"account_id": 103, "meta_heroes": [3], "pub_known": True},
        {"account_id": 104, "meta_heroes": [], "pub_known": True},
        {"account_id": 105, "meta_heroes": [], "pub_known": False},
    ]
    # Heroes 1 and 2 were picked 3 times; hero 3 was never picked by the team, so it is not listed
    assert [h["hero_id"] for h in meta["heroes"]] == [1, 2]


def test_league_games_alone_prove_practice():
    # 3 league games on hero 1 (player 101) and hero 2 (player 102) are enough, 4 pub games are not
    meta = _meta(_games(3, TWO_META), {101: {}, 102: {}, 103: {3: 4}, 104: {}, 105: {}})

    assert [p["meta_heroes"] for p in meta["players"]] == [[1], [2], [], [], []]
    assert meta["state"] == STATE_NO_INFO


def test_no_info_without_games():
    meta = _meta([])

    assert meta["state"] == STATE_NO_INFO
    assert meta["deep"]["meta_games_pct"] is None
    assert meta["heroes"] == []


def test_heroes_list_counts_recent_and_deep_picks_with_ultra_flag():
    games = [*_games(2, THREE_META), _game(50, 40, [4, 2, 6, 7, 8])]

    heroes = {h["hero_id"]: h for h in _meta(games, meta_hero_min_games=1)["heroes"]}

    assert set(heroes) == {1, 2, 3, 4}  # Non-meta heroes are not listed
    assert heroes[1] == {
        "hero_id": 1,
        "localized_name": "Hero 1",
        "icon": "https://cdn/hero1.png",
        "ultra": True,
        "games": 2,
        "recent_games": 2,
        "practice_players": 0,
    }
    assert (heroes[2]["games"], heroes[2]["recent_games"]) == (3, 2)
    assert (heroes[4]["games"], heroes[4]["recent_games"], heroes[4]["ultra"]) == (1, 0, False)
    assert _meta(games, meta_hero_min_games=1)["heroes"][0]["hero_id"] == 2  # Most games first


def test_heroes_picked_fewer_than_three_times_are_not_listed():
    games = [*_games(2, THREE_META), _game(50, 40, [4, 2, 6, 7, 8])]  # Hero 2: 3 picks, heroes 1 and 3: 2, hero 4: 1

    assert [h["hero_id"] for h in _meta(games)["heroes"]] == [2]
    # Practice alone does not list a hero; it is counted for the listed ones
    practised = _meta(games, {101: {4: 5}, 102: {2: 9}, 103: {}, 104: {}, 105: {}})
    assert [(h["hero_id"], h["practice_players"]) for h in practised["heroes"]] == [(2, 1)]
    # The state still counts every pick
    assert _meta(games)["recent"]["meta_games"] == 2


def test_stand_in_picks_count_for_the_team():
    games = [_game(i, 1 + i * 0.5, THREE_META, players=[101, 102, 999, 104, 105]) for i in range(20)]

    meta = _meta(games)

    assert meta["state"] == STATE_ACTIVELY
    assert next(h for h in meta["heroes"] if h["hero_id"] == 3)["games"] == 20


# --- Loading the games ---


def _match(match_id: int, days_ago: float, radiant: bool = True) -> TeamMatch:
    return TeamMatch(match_id=match_id, start_time=int(NOW - days_ago * DAY), leagueid=1, radiant=radiant)


def _lineup(radiant_heroes: list[int | None]) -> list[LineupPlayer]:
    radiant = [LineupPlayer(i, CORE[i], None, None, h) for i, h in enumerate(radiant_heroes)]
    dire = [LineupPlayer(128 + i, 200 + i, None, None, 50 + i) for i in range(5)]
    return radiant + dire


def test_load_team_games_cuts_windows_at_patch_and_skips_unknown_heroes():
    matches = [_match(1, 1), _match(2, 5, radiant=False), _match(3, 8), _match(4, 30)]
    lineups = {1: _lineup(THREE_META), 2: _lineup(THREE_META), 3: _lineup([1, 2, 3, 4, None])}
    patch_start = NOW - 10 * DAY

    with (
        patch("backend.team_meta.latest_patch", return_value={"name": "7.40", "start_time": patch_start}),
        patch("backend.team_meta.get_team_league_matches", return_value=matches),
        patch("backend.team_meta.get_match_lineups", return_value=lineups) as get_lineups,
    ):
        games = load_team_games(7, 20, TeamMetaParams(), now=NOW)

    # Match 4 is older than the patch and is not looked up; match 3 misses a hero
    assert list(get_lineups.call_args.args[0]) == [1, 2, 3]
    assert games["patch"] == "7.40"
    assert (games["recent_start"], games["deep_start"]) == (patch_start, patch_start)
    assert [g["match_id"] for g in games["games"]] == [1, 2]
    assert games["games"][0]["picks"] == [[a, h] for a, h in zip(CORE, THREE_META, strict=True)]
    assert games["games"][1]["picks"] == [[200 + i, 50 + i] for i in range(5)]  # Dire side


def test_load_team_games_without_patch_cut():
    with (
        patch("backend.team_meta.latest_patch") as patches,
        patch("backend.team_meta.get_team_league_matches", return_value=[]),
    ):
        games = load_team_games(7, 20, TeamMetaParams(patch_cut=False, deep_days=45), now=NOW)

    patches.assert_not_called()
    assert (games["recent_start"], games["deep_start"], games["games"]) == (NOW - 20 * DAY, NOW - 45 * DAY, [])


def test_latest_patch_is_the_newest_released_and_cached():
    answer = [
        {"name": "7.38", "date": "2025-02-19T00:00:00Z", "id": 56},
        {"name": "7.39", "date": "2025-05-22T00:00:00Z", "id": 57},
        {"name": "9.99", "date": "2099-01-01T00:00:00Z", "id": 99},
        {"bad": True},
    ]
    with patch("backend.team_meta.get_json", return_value=answer) as get_json:
        first = latest_patch(NOW)
        second = latest_patch(NOW)

    assert first == second == {"name": "7.39", "start_time": 1747872000}
    get_json.assert_called_once()


def test_latest_patch_failure_is_none_and_cached_briefly(fake_redis):
    with patch("backend.team_meta.get_json", side_effect=OpenDotaError(503, "NETWORK_ERROR", "down")) as get_json:
        assert latest_patch(NOW) is None
        assert latest_patch(NOW) is None

    get_json.assert_called_once()
    assert 0 < fake_redis.ttl(PATCHES_KEY) <= 60


def test_player_heroes_are_cached_and_errors_are_not():
    answer = [{"hero_id": 1, "games": 4}, {"hero_id": "2", "games": 0}, {"hero_id": 3, "games": 7}, "bad"]
    with patch("backend.team_meta.get_json", return_value=answer) as get_json:
        assert get_player_heroes_cached(101, 60) == {1: 4, 3: 7}
        assert get_player_heroes_cached(101, 60) == {1: 4, 3: 7}
    get_json.assert_called_once()
    assert get_json.call_args.args[0] == "/players/101/heroes"
    assert get_json.call_args.kwargs["params"] == {"date": 60}

    with patch("backend.team_meta.get_json", side_effect=OpenDotaError(429, "HTTP_ERROR", "limit")) as get_json:
        for _ in range(2):
            with pytest.raises(OpenDotaError):
                get_player_heroes_cached(102, 60)
    assert get_json.call_count == 2


def test_player_heroes_days_covers_the_window():
    assert player_heroes_days(NOW - 60 * DAY, now=NOW) == 60
    assert player_heroes_days(NOW - int(9.2 * DAY), now=NOW) == 10
    assert player_heroes_days(NOW, now=NOW) == 1


# --- Task step, compute_statistics and the route ---


def _run_task(team_meta: dict | None, player_heroes=None, hero_stats=None):
    def fake_player_heroes(account_id, days, on_wait=None):
        if isinstance(player_heroes, Exception):
            raise player_heroes
        return {1: 9}

    with (
        patch("backend.task_store.update_progress") as progress,
        patch.object(tasks, "store_results") as store,
        patch.object(tasks, "get_matches_cached", return_value=[]),
        patch.object(tasks, "get_rank_cached", return_value=None),
        patch.object(tasks, "get_team_matches_summary", return_value=MatchesSummary()),
        patch.object(tasks, "get_player_heroes_cached", side_effect=fake_player_heroes) as heroes,
        patch.object(tasks, "cached_hero_stats", return_value=(HERO_STATS, NOW), side_effect=hero_stats),
        patch.object(tasks.time, "sleep"),
    ):
        tasks.players_statistics_task.run("t1", CORE, 20, team_meta=team_meta)
    return progress, store.call_args.args[1], heroes


TEAM_META_INPUT = {
    "games": _team_games(_games(20, THREE_META)),
    "core": CORE,
    "meta_params": MetaParams().__dict__,
    "params": TeamMetaParams().__dict__,
}


def test_task_adds_meta_to_results_with_a_step_per_core_player():
    progress, results, heroes = _run_task(TEAM_META_INPUT)

    assert results["meta"]["state"] == STATE_ACTIVELY
    # Hero 1 from the player heroes (9 games); 102 and 103 also have 20 league games on heroes 2 and 3
    assert [p["meta_heroes"] for p in results["meta"]["players"]] == [[1], [1, 2], [1, 3], [1], [1]]
    assert heroes.call_count == 5
    total_steps = 2 + 2 * 5 + 5
    assert progress.call_args_list[-1].args[1] == total_steps  # The final message


def test_task_meta_survives_player_heroes_errors():
    _, results, _ = _run_task(TEAM_META_INPUT, player_heroes=OpenDotaError(503, "NETWORK_ERROR", "down"))

    assert results["meta"]["state"] == STATE_ACTIVELY
    assert all(p["pub_known"] is False for p in results["meta"]["players"])


def test_task_meta_error_without_hero_stats():
    _, results, _ = _run_task(TEAM_META_INPUT, hero_stats=ConnectionError("heroStats down"))

    assert results["meta"] == {"error": "heroStats down"}


def test_task_without_team_meta_stores_null():
    _, results, heroes = _run_task(None)

    assert results["meta"] is None
    heroes.assert_not_called()


def test_create_team_stats_sends_team_games_and_core_to_task(no_team_meta_requests):
    from backend.models import TeamRoster
    from backend.stats import _create_team_stats

    players = [Player(id=a, name=str(a), games=5, is_core=a != 105) for a in CORE]
    roster = TeamRoster(players=players, other_players=[])
    no_team_meta_requests.return_value = {"games": []}
    task = MagicMock()
    params = TeamMetaParams(deep_days=45)
    with (
        patch("backend.stats.resolve_roster", return_value=roster),
        patch("backend.stats.get_players_by_team", return_value=([], [])),
        patch("backend.task_store.update_progress"),
    ):
        _create_team_stats(
            TeamStats(team_id=7), task, days=30, meta_params=MetaParams(pub_top=10), team_meta_params=params
        )

    assert no_team_meta_requests.call_args.args == (7, 30, params)
    team_meta = task.delay.call_args.kwargs["team_meta"]
    assert team_meta["core"] == [101, 102, 103, 104]
    assert team_meta["games"] == {"games": []}
    assert team_meta["meta_params"]["pub_top"] == 10
    assert team_meta["params"]["deep_days"] == 45


def test_create_team_stats_without_team_games_skips_meta():
    from backend.models import TeamRoster
    from backend.stats import _create_team_stats

    task = MagicMock()
    with (
        patch("backend.stats.resolve_roster", return_value=TeamRoster(players=[Player(id=1, name="a", games=1)])),
        patch("backend.stats.get_players_by_team", return_value=([], [])),
        patch("backend.task_store.update_progress"),
    ):
        _create_team_stats(TeamStats(team_id=7), task)

    assert task.delay.call_args.kwargs["team_meta"] is None


def test_statistics_route_forwards_meta_settings(monkeypatch):
    from backend import create_app
    from backend.models import StatsResponse

    seen = []

    def fake_compute(teams=None, team_ids=None, days=20, meta_params=None, team_meta_params=None):
        seen.append((meta_params, team_meta_params))
        return StatsResponse(teams=[])

    monkeypatch.setattr("backend.routes.statistics.compute_statistics", fake_compute)
    client = create_app(test_config={}).test_client()

    assert client.get("/api/statistics?team=A").status_code == 200
    url = "/api/statistics?team=A&pro_min_pick_ban=20&deep_days=45&meta_min_games=12&patch_cut=false"
    assert client.get(url).status_code == 200
    assert client.get("/api/statistics?team=A&meta_min_heroes=6").status_code == 422

    assert seen[0] == (MetaParams(), TeamMetaParams())
    assert seen[1][0] == MetaParams(pro_min_pick_ban=20)
    assert seen[1][1] == TeamMetaParams(deep_days=45, meta_min_games=12, patch_cut=False)


def test_hero_meta_route_adds_the_latest_patch(monkeypatch):
    from backend import create_app

    monkeypatch.setattr("backend.routes.catalog.get_meta", lambda params, refresh: {"heroes": []})
    monkeypatch.setattr("backend.routes.catalog.latest_patch", lambda now: {"name": "7.41", "start_time": 1})
    client = create_app(test_config={}).test_client()

    assert client.get("/api/heroes/meta").get_json() == {"heroes": [], "patch": "7.41"}

"""Tests for roster resolution from recent league matches (backend.rosters)."""

from unittest.mock import MagicMock, patch

import pytest

from backend.opendota import RATE_LIMIT_RETRIES, opendota_get
from backend.pro_players import get_d2ba_db
from backend.rosters import (
    TEAM_MATCHES_TTL,
    TeamMatch,
    classify_roster,
    compute_league_form,
    get_match_lineup,
    get_team_league_matches,
    resolve_roster,
)

NOW = 1_792_300_000
DAY = 24 * 60 * 60
TEAM_ID = 2576071

RADIANT_PLAYERS = [101, 102, 103, 104, 105]
DIRE_PLAYERS = [201, 202, 203, 204, 205]


def _team_match(match_id: int, start_time: int, opponent: int, radiant: bool = True, won: bool = True) -> dict:
    return {
        "match_id": match_id,
        "start_time": start_time,
        "leagueid": 19944,
        "league_name": "EPL Masters 2026 ",
        "radiant": radiant,
        "radiant_win": won if radiant else not won,
        "opposing_team_id": opponent,
        "opposing_team_name": f"Team {opponent}",
    }


def _explorer_rows(radiant: list[int], dire: list[int], match_id: int = 0) -> list[dict]:
    rows = [{"match_id": match_id, "player_slot": i, "account_id": a} for i, a in enumerate(radiant)]
    rows += [{"match_id": match_id, "player_slot": 128 + i, "account_id": a} for i, a in enumerate(dire)]
    return rows


def _response(payload, status: int = 200, headers: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.headers = headers or {}
    return resp


class FakeOpenDota:
    """Minimal fake of the OpenDota endpoints used by backend.rosters."""

    def __init__(self, team_matches: list[dict], lineups: dict[int, tuple[list[int], list[int]]]):
        self.team_matches = team_matches
        self.lineups = lineups  # match_id -> (radiant accounts, dire accounts)
        self.calls: list[str] = []
        self.explorer_batches: list[list[int]] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(url)
        if url.endswith(f"/teams/{TEAM_ID}/matches"):
            return _response(self.team_matches)
        if url.endswith("/explorer"):
            ids = [int(x) for x in params["sql"].split("IN (", 1)[1].rstrip(")").split(",")]
            self.explorer_batches.append(ids)
            rows = [row for i in ids if i in self.lineups for row in _explorer_rows(*self.lineups[i], match_id=i)]
            return _response({"rows": rows, "err": None})
        if "/matches/" in url:
            return _response({"players": []})
        return _response(None, status=404)


@pytest.fixture
def ctx(app):
    with app.app_context():
        yield


def _store_names(names: dict[int, str]) -> None:
    db = get_d2ba_db()
    db.executemany("INSERT INTO pro_players (account_id, name) VALUES (?, ?)", list(names.items()))
    db.commit()


def _games(*lineups: list[int], start_days: float = 1, step_days: float = 1) -> tuple[list[dict], dict]:
    """League games newest first, one per day, with the given team lineups on Radiant."""
    matches, lineup_map = [], {}
    for i, accounts in enumerate(lineups):
        match_id = 1000 - i
        matches.append(_team_match(match_id, int(NOW - (start_days + i * step_days) * DAY), opponent=i))
        lineup_map[match_id] = (accounts, DIRE_PLAYERS)
    return matches, lineup_map


def test_roster_is_taken_from_team_side(ctx):
    """The roster is taken from the team's side of its league games (Dire here)."""
    fake = FakeOpenDota(
        [_team_match(3, NOW - DAY, opponent=9, radiant=False)],
        {3: (DIRE_PLAYERS, RADIANT_PLAYERS)},
    )
    _store_names({101: "rincyq", 102: "aik"})

    with patch("backend.opendota.requests.get", side_effect=fake.get):
        roster = resolve_roster(TEAM_ID, now=NOW)

    assert [p.id for p in roster.players] == RADIANT_PLAYERS
    assert [p.name for p in roster.players][:3] == ["rincyq", "aik", "#103"]
    assert [p.games for p in roster.players] == [1] * 5
    assert roster.last_match_id == 3
    assert roster.other_players == []
    assert roster.standins_count == 0  # no older league game, so time on the team is unknown
    assert roster.roster_state is None
    assert roster.games_checked == 1


def test_roster_is_players_with_most_games_not_latest_lineup(ctx):
    """105 played 7 of 10 games, 999 only 3 (including the latest): 105 is in the roster, 999 is another player."""
    with_105 = [101, 102, 103, 104, 105]
    with_999 = [101, 102, 103, 104, 999]
    matches, lineups = _games(
        with_999, with_105, with_999, with_105, with_105, with_999, with_105, with_105, with_105, with_105
    )
    fake = FakeOpenDota(matches, lineups)
    with patch("backend.opendota.requests.get", side_effect=fake.get):
        roster = resolve_roster(TEAM_ID, now=NOW)

    assert sorted(p.id for p in roster.players) == with_105
    assert {p.id: p.games for p in roster.players}[105] == 7
    assert [(p.id, p.games) for p in roster.other_players] == [(999, 3)]
    assert roster.games_checked == 10
    assert roster.last_match_id == 1000  # 4 of the 5 main players played the latest game
    assert roster.latest_match_time == NOW - DAY
    assert roster.latest_match_standins == 1  # 999 is not in the core
    assert len(fake.explorer_batches) == 1  # all 10 lineups in one explorer query


def test_tie_goes_to_the_player_who_played_more_recently(ctx):
    matches, lineups = _games([101, 102, 103, 104, 106], [101, 102, 103, 104, 105])
    fake = FakeOpenDota(matches, lineups)
    with patch("backend.opendota.requests.get", side_effect=fake.get):
        roster = resolve_roster(TEAM_ID, now=NOW)

    assert [p.id for p in roster.players][-1] == 106
    assert [p.id for p in roster.other_players] == [105]


def test_last_match_of_roster_skips_games_played_mostly_by_others(ctx):
    """The newest game had only 2 main players, so the roster's last game is the one before it."""
    main = [101, 102, 103, 104, 105]
    matches, lineups = _games([101, 102, 301, 302, 303], main, main, main, main, main)
    fake = FakeOpenDota(matches, lineups)
    with patch("backend.opendota.requests.get", side_effect=fake.get):
        roster = resolve_roster(TEAM_ID, now=NOW)

    assert sorted(p.id for p in roster.players) == main
    assert roster.last_match_id == 999
    assert roster.last_match_time == NOW - 2 * DAY
    assert roster.latest_match_standins == 3


def test_standins_and_core_by_time_on_team(ctx):
    """999 first played 5 days ago (stand-in), 104 first played 25 days ago (neither), 101-103 70 days ago (core).

    105 only played before the window, so it is a former player and is left out.
    """
    newest = [101, 102, 103, 104, 999]
    fake = FakeOpenDota(
        [
            _team_match(30, NOW - 1 * DAY, opponent=1),
            _team_match(20, NOW - 5 * DAY, opponent=2),
            _team_match(10, NOW - 25 * DAY, opponent=3),
            _team_match(5, NOW - 70 * DAY, opponent=4),
        ],
        {
            30: (newest, DIRE_PLAYERS),
            20: (newest, DIRE_PLAYERS),
            10: ([101, 102, 103, 104, 105], DIRE_PLAYERS),
            5: ([101, 102, 103, 401, 402], DIRE_PLAYERS),
        },
    )
    with patch("backend.opendota.requests.get", side_effect=fake.get):
        roster = resolve_roster(TEAM_ID, now=NOW)

    assert sorted(p.id for p in roster.players) == sorted(newest)
    assert roster.other_players == []
    assert [p.id for p in roster.players if p.is_new] == [999]
    assert roster.new_players_count == 1
    assert roster.standins_count == 0  # all 5 played every window game, so all are core
    assert roster.core_count == 3
    assert roster.games_checked == 2
    assert roster.roster_state == "new_team"  # the stand-in played both window games
    assert fake.explorer_batches == [[30, 20, 10, 5]]  # window games and both tenure samples in one query


def test_standin_outside_core_means_new_players(ctx):
    """999 joined 2 days ago and played 1 of 4 window games; 105 played 3 of 4 (75%), so 999 is not in the core."""
    fake = FakeOpenDota(
        [
            _team_match(30, NOW - 1 * DAY, opponent=1),
            _team_match(20, NOW - 3 * DAY, opponent=2),
            _team_match(15, NOW - 4 * DAY, opponent=2),
            _team_match(12, NOW - 5 * DAY, opponent=2),
            _team_match(10, NOW - 25 * DAY, opponent=3),
        ],
        {
            30: ([101, 102, 103, 104, 999], DIRE_PLAYERS),
            20: (RADIANT_PLAYERS, DIRE_PLAYERS),
            15: (RADIANT_PLAYERS, DIRE_PLAYERS),
            12: (RADIANT_PLAYERS, DIRE_PLAYERS),
            10: (RADIANT_PLAYERS, DIRE_PLAYERS),
        },
    )
    with patch("backend.opendota.requests.get", side_effect=fake.get):
        roster = resolve_roster(TEAM_ID, now=NOW)

    assert [p.id for p in roster.players] == RADIANT_PLAYERS
    assert all(p.is_core for p in roster.players)
    assert [(p.id, p.is_new, p.is_core) for p in roster.other_players] == [(999, True, False)]
    assert roster.new_players_count == 0  # 999 is outside the main 5
    assert roster.standins_count == 1  # 999: new and outside the core
    assert roster.roster_state == "new_players"


@pytest.mark.parametrize(
    "games,total,standins,core,state",
    [
        # 5 players with 75%+ of the games, no stand-ins
        ({1: 10, 2: 10, 3: 9, 4: 8, 5: 8, 6: 2}, 10, set(), {1, 2, 3, 4, 5}, "stable"),
        # stand-in with 2 of 10 games is outside the core
        ({1: 10, 2: 10, 3: 10, 4: 10, 5: 8, 6: 2}, 10, {6}, {1, 2, 3, 4, 5}, "new_players"),
        # stand-in with 28 of 30 games is in the core
        ({1: 30, 2: 28, 3: 28, 4: 28, 5: 28, 6: 2}, 30, {2}, {1, 2, 3, 4, 5}, "new_team"),
        # only 4 players reach 75%; 50% gives 5
        ({1: 10, 2: 10, 3: 10, 4: 10, 5: 6, 6: 4}, 10, {6}, {1, 2, 3, 4, 5}, "new_players"),
        # no share gives exactly 5 players: no clear core
        ({1: 4, 2: 4, 3: 4, 4: 4, 5: 2, 6: 2}, 4, {6}, set(), "new_team"),
        # 6 players with 75%+: no clear core
        ({1: 4, 2: 4, 3: 4, 4: 4, 5: 3, 6: 3}, 4, {6}, set(), "new_team"),
    ],
)
def test_classify_roster(games, total, standins, core, state):
    assert classify_roster(games, total, standins) == (core, state)


def test_new_player_between_thresholds_is_not_a_standin(ctx):
    """A player who joined 30 days ago is neither a stand-in nor core."""
    fake = FakeOpenDota(
        [
            _team_match(30, NOW - 1 * DAY, opponent=1),
            _team_match(10, NOW - 30 * DAY, opponent=3),
            _team_match(5, NOW - 70 * DAY, opponent=4),
        ],
        {
            30: (RADIANT_PLAYERS, DIRE_PLAYERS),
            10: (RADIANT_PLAYERS, DIRE_PLAYERS),
            5: ([101, 102, 103, 104, 401], DIRE_PLAYERS),
        },
    )
    with patch("backend.opendota.requests.get", side_effect=fake.get):
        roster = resolve_roster(TEAM_ID, now=NOW)

    assert roster.standins_count == 0
    assert roster.core_count == 4
    assert roster.roster_state == "stable"


def test_lineups_are_fetched_in_batches(ctx):
    """25 games in the window need two explorer queries (20 + 5), and none the second time."""
    matches, lineups = _games(*[RADIANT_PLAYERS] * 25, start_days=0.5, step_days=0.5)
    fake = FakeOpenDota(matches, lineups)
    with patch("backend.opendota.requests.get", side_effect=fake.get):
        roster = resolve_roster(TEAM_ID, now=NOW)
        resolve_roster(TEAM_ID, now=NOW + 60)

    assert roster.games_checked == 25
    assert [len(batch) for batch in fake.explorer_batches] == [20, 5]


def test_no_recent_league_match_returns_empty_roster(ctx):
    fake = FakeOpenDota([_team_match(1, NOW - 90 * DAY, opponent=9)], {})
    with patch("backend.opendota.requests.get", side_effect=fake.get):
        roster = resolve_roster(TEAM_ID, days=60, now=NOW)

    assert roster.players == []
    assert roster.league_form is not None
    assert roster.league_form.matches == 0
    assert all(not url.endswith("/explorer") for url in fake.calls)


def test_api_failure_returns_empty_roster(ctx):
    with patch("backend.opendota.requests.get", side_effect=ConnectionError("down")):
        roster = resolve_roster(TEAM_ID, now=NOW)
    assert roster.players == []


def test_second_call_uses_cache(ctx):
    fake = FakeOpenDota(
        [_team_match(3, NOW - DAY, opponent=9)],
        {3: (RADIANT_PLAYERS, DIRE_PLAYERS)},
    )
    with patch("backend.opendota.requests.get", side_effect=fake.get):
        first = resolve_roster(TEAM_ID, now=NOW)
        calls_after_first = len(fake.calls)
        second = resolve_roster(TEAM_ID, now=NOW + 60)

    assert calls_after_first == 2
    assert len(fake.calls) == 2
    assert first.players == second.players


def test_team_matches_refetched_after_ttl(ctx):
    fake = FakeOpenDota([_team_match(3, NOW - DAY, opponent=9)], {})
    with patch("backend.opendota.requests.get", side_effect=fake.get):
        get_team_league_matches(TEAM_ID, now=NOW)
        get_team_league_matches(TEAM_ID, now=NOW + TEAM_MATCHES_TTL + 1)
    assert sum(1 for url in fake.calls if url.endswith("/matches")) == 2


def test_lineup_falls_back_to_match_endpoint(ctx):
    players = [{"player_slot": s, "account_id": 1000 + s} for s in [0, 1, 2, 3, 4, 128, 129, 130, 131, 132]]

    def fake_get(url, params=None, timeout=None):
        if url.endswith("/explorer"):
            return _response({"rows": []})
        return _response({"players": players})

    with patch("backend.opendota.requests.get", side_effect=fake_get):
        lineup = get_match_lineup(42)

    assert len(lineup) == 10
    assert (128, 1128) in lineup


def test_incomplete_lineup_is_not_cached(ctx):
    with patch("backend.opendota.requests.get", return_value=_response({"rows": []})) as mock_get:
        assert get_match_lineup(42) == []
        get_match_lineup(42)
    assert mock_get.call_count == 4  # explorer + /matches fallback, twice


def test_league_form_counts_wins_on_both_sides():
    matches = [
        TeamMatch(match_id=1, start_time=NOW - DAY, radiant=True, radiant_win=True, leagueid=1),
        TeamMatch(match_id=2, start_time=NOW - 2 * DAY, radiant=False, radiant_win=True, leagueid=1),
        TeamMatch(match_id=3, start_time=NOW - 3 * DAY, radiant=False, radiant_win=False, leagueid=1),
        TeamMatch(match_id=4, start_time=NOW - 100 * DAY, radiant=True, radiant_win=True, leagueid=1),
    ]
    form = compute_league_form(matches, days=60, now=NOW)
    assert (form.matches, form.wins, form.losses) == (3, 2, 1)
    assert form.win_percentage == pytest.approx(66.666, rel=1e-3)
    assert form.last_match_time == NOW - DAY


def test_create_team_stats_uses_recent_lineup(ctx):
    from backend.pro_players import Player
    from backend.rosters import LeagueForm, TeamRoster
    from backend.stats import TeamStats, _create_team_stats

    roster = TeamRoster(
        players=[Player(id=1, name="a", games=3), Player(id=2, name="b", games=2)],
        other_players=[Player(id=5, name="backup", games=1)],
        standins_count=1,
        core_count=1,
        games_checked=3,
        last_match_time=NOW - DAY,
        latest_match_time=NOW,
        latest_match_standins=2,
        league_form=LeagueForm(days=60, matches=3, wins=2, losses=1, win_percentage=66.7),
    )
    task = MagicMock()
    with (
        patch("backend.stats.resolve_roster", return_value=roster),
        patch(
            "backend.stats.get_players_by_team",
            return_value=([Player(id=1, name="a"), Player(id=7, name="old")], []),
        ),
    ):
        stats = _create_team_stats(TeamStats(team_id=TEAM_ID), task)

    assert stats.roster_source == "recent_matches"
    assert [p.id for p in stats.players] == [1, 2]
    assert [p.id for p in stats.other_players] == [5]  # former member 7 from pro_players is dropped
    assert stats.standins_count == 1
    assert stats.core_count == 1
    assert stats.roster_games == 3
    assert stats.roster_last_match_time == NOW - DAY
    assert (stats.latest_match_time, stats.latest_match_standins) == (NOW, 2)
    assert stats.other_players[0].games == 1
    assert stats.league_form is not None and stats.league_form.wins == 2
    task.delay.assert_called_once()
    assert task.delay.call_args.kwargs["accounts"] == [1, 2]


def test_create_team_stats_falls_back_to_pro_players(ctx):
    from backend.pro_players import Player
    from backend.rosters import TeamRoster
    from backend.stats import TeamStats, _create_team_stats

    task = MagicMock()
    with (
        patch("backend.stats.resolve_roster", side_effect=RuntimeError("boom")),
        patch("backend.stats.get_players_by_team", return_value=([Player(id=7, name="old")], [])),
    ):
        stats = _create_team_stats(TeamStats(team_id=TEAM_ID), task)

    assert stats.roster_source == "pro_players"
    assert [p.id for p in stats.players] == [7]
    assert stats.league_form is None
    assert TeamRoster().players == []


def test_roster_window_follows_days_argument(ctx):
    """A lineup older than the window is ignored; the default window is 20 days like the match history."""
    fake = FakeOpenDota(
        [_team_match(3, NOW - 30 * DAY, opponent=9)],
        {3: (RADIANT_PLAYERS, DIRE_PLAYERS)},
    )
    with patch("backend.opendota.requests.get", side_effect=fake.get):
        assert resolve_roster(TEAM_ID, now=NOW).players == []
        assert [p.id for p in resolve_roster(TEAM_ID, days=60, now=NOW).players] == RADIANT_PLAYERS


def test_create_team_stats_passes_days_to_roster_and_task(ctx):
    from backend.pro_players import Player
    from backend.rosters import TeamRoster
    from backend.stats import TeamStats, _create_team_stats

    task = MagicMock()
    with (
        patch("backend.stats.resolve_roster", return_value=TeamRoster(players=[Player(id=1, name="a")])) as resolve,
        patch("backend.stats.get_players_by_team", return_value=([], [])),
    ):
        _create_team_stats(TeamStats(team_id=TEAM_ID), task, days=45)

    assert resolve.call_args.kwargs["days"] == 45
    assert task.delay.call_args.kwargs["days"] == 45


def test_rate_limited_request_is_postponed_and_repeated():
    waits: list[int] = []
    responses = [_response(None, status=429, headers={"Retry-After": "7"}), _response(None, status=429), _response([])]
    with (
        patch("backend.opendota.requests.get", side_effect=responses) as mock_get,
        patch("backend.opendota.time.sleep") as mock_sleep,
    ):
        resp = opendota_get("https://api.opendota.com/api/teams/1/matches", on_wait=waits.append)

    assert resp.status_code == 200
    assert mock_get.call_count == 3
    assert waits == [7, 20]  # Retry-After first, then the default backoff for the second repeat
    assert [c.args[0] for c in mock_sleep.call_args_list] == [7, 20]


def test_rate_limit_gives_up_after_retries():
    with (
        patch("backend.opendota.requests.get", return_value=_response(None, status=429)) as mock_get,
        patch("backend.opendota.time.sleep"),
    ):
        resp = opendota_get("https://api.opendota.com/api/teams/1/matches")

    assert resp.status_code == 429
    assert mock_get.call_count == RATE_LIMIT_RETRIES + 1

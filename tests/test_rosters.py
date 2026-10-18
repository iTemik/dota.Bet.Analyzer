"""Tests for roster resolution from recent league matches (backend.rosters)."""

from unittest.mock import MagicMock, patch

import pytest

from backend.pro_players import get_d2ba_db
from backend.rosters import (
    TEAM_MATCHES_TTL,
    TeamMatch,
    _latest_match_per_series,
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


def _explorer_rows(radiant: list[int], dire: list[int]) -> dict:
    rows = [{"player_slot": i, "account_id": a} for i, a in enumerate(radiant)]
    rows += [{"player_slot": 128 + i, "account_id": a} for i, a in enumerate(dire)]
    return {"rows": rows, "err": None}


def _response(payload, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    return resp


class FakeOpenDota:
    """Minimal fake of the OpenDota endpoints used by backend.rosters."""

    def __init__(self, team_matches: list[dict], lineups: dict[int, dict]):
        self.team_matches = team_matches
        self.lineups = lineups
        self.calls: list[str] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(url)
        if url.endswith(f"/teams/{TEAM_ID}/matches"):
            return _response(self.team_matches)
        if url.endswith("/explorer"):
            match_id = int(params["sql"].rsplit("=", 1)[1])
            return _response(self.lineups.get(match_id, {"rows": []}))
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


def test_roster_is_latest_lineup_on_team_side(ctx):
    """The roster is taken from the team's side of the latest league match (Dire here)."""
    fake = FakeOpenDota(
        [_team_match(3, NOW - DAY, opponent=9, radiant=False)],
        {3: _explorer_rows(DIRE_PLAYERS, RADIANT_PLAYERS)},
    )
    _store_names({101: "rincyq", 102: "aik"})

    with patch("backend.rosters.requests.get", side_effect=fake.get):
        roster = resolve_roster(TEAM_ID, now=NOW)

    assert [p.id for p in roster.players] == RADIANT_PLAYERS
    assert [p.name for p in roster.players][:3] == ["rincyq", "aik", "#103"]
    assert roster.last_match_id == 3
    assert roster.other_players == []
    assert roster.standins_count == 0  # no older league game, so time on the team is unknown
    assert roster.series_checked == 1


def test_players_others_standins_and_core_by_time_on_team(ctx):
    """Latest lineup = players; other active players go to other_players; former players are dropped.

    Time on the team: 999 first played 1 day ago (stand-in), 104 first played 25 days ago (neither),
    101-103 already played 70 days ago (core).
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
            30: _explorer_rows(newest, DIRE_PLAYERS),
            20: _explorer_rows([101, 102, 103, 104, 105], DIRE_PLAYERS),
            10: _explorer_rows([101, 102, 103, 104, 105], DIRE_PLAYERS),
            5: _explorer_rows([101, 102, 103, 401, 402], DIRE_PLAYERS),
        },
    )
    with patch("backend.rosters.requests.get", side_effect=fake.get):
        roster = resolve_roster(TEAM_ID, now=NOW)

    assert [p.id for p in roster.players] == newest
    assert [p.id for p in roster.other_players] == [105]  # active in the window; 401/402 are former players
    assert roster.standins_count == 1
    assert roster.core_count == 3
    assert roster.series_checked == 2
    assert sum(1 for url in fake.calls if url.endswith("/explorer")) == 4


def test_new_player_between_thresholds_is_not_a_standin(ctx):
    """A player who joined 30 days ago is neither a stand-in nor core."""
    fake = FakeOpenDota(
        [
            _team_match(30, NOW - 1 * DAY, opponent=1),
            _team_match(10, NOW - 30 * DAY, opponent=3),
            _team_match(5, NOW - 70 * DAY, opponent=4),
        ],
        {
            30: _explorer_rows(RADIANT_PLAYERS, DIRE_PLAYERS),
            10: _explorer_rows(RADIANT_PLAYERS, DIRE_PLAYERS),
            5: _explorer_rows([101, 102, 103, 104, 401], DIRE_PLAYERS),
        },
    )
    with patch("backend.rosters.requests.get", side_effect=fake.get):
        roster = resolve_roster(TEAM_ID, now=NOW)

    assert roster.standins_count == 0
    assert roster.core_count == 4


def test_games_of_one_series_need_one_lineup_request(ctx):
    """A Bo3 against the same opponent counts as one series, so only its newest game is looked up."""
    fake = FakeOpenDota(
        [
            _team_match(3, NOW - DAY, opponent=9),
            _team_match(2, NOW - DAY - 3600, opponent=9),
            _team_match(1, NOW - DAY - 7200, opponent=9),
        ],
        {3: _explorer_rows(RADIANT_PLAYERS, DIRE_PLAYERS)},
    )
    with patch("backend.rosters.requests.get", side_effect=fake.get):
        roster = resolve_roster(TEAM_ID, now=NOW)

    assert roster.series_checked == 1
    assert sum(1 for url in fake.calls if url.endswith("/explorer")) == 1


def test_no_recent_league_match_returns_empty_roster(ctx):
    fake = FakeOpenDota([_team_match(1, NOW - 90 * DAY, opponent=9)], {})
    with patch("backend.rosters.requests.get", side_effect=fake.get):
        roster = resolve_roster(TEAM_ID, days=60, now=NOW)

    assert roster.players == []
    assert roster.league_form is not None
    assert roster.league_form.matches == 0
    assert all(not url.endswith("/explorer") for url in fake.calls)


def test_api_failure_returns_empty_roster(ctx):
    with patch("backend.rosters.requests.get", side_effect=ConnectionError("down")):
        roster = resolve_roster(TEAM_ID, now=NOW)
    assert roster.players == []


def test_second_call_uses_cache(ctx):
    fake = FakeOpenDota(
        [_team_match(3, NOW - DAY, opponent=9)],
        {3: _explorer_rows(RADIANT_PLAYERS, DIRE_PLAYERS)},
    )
    with patch("backend.rosters.requests.get", side_effect=fake.get):
        first = resolve_roster(TEAM_ID, now=NOW)
        calls_after_first = len(fake.calls)
        second = resolve_roster(TEAM_ID, now=NOW + 60)

    assert calls_after_first == 2
    assert len(fake.calls) == 2
    assert first.players == second.players


def test_team_matches_refetched_after_ttl(ctx):
    fake = FakeOpenDota([_team_match(3, NOW - DAY, opponent=9)], {})
    with patch("backend.rosters.requests.get", side_effect=fake.get):
        get_team_league_matches(TEAM_ID, now=NOW)
        get_team_league_matches(TEAM_ID, now=NOW + TEAM_MATCHES_TTL + 1)
    assert sum(1 for url in fake.calls if url.endswith("/matches")) == 2


def test_lineup_falls_back_to_match_endpoint(ctx):
    players = [{"player_slot": s, "account_id": 1000 + s} for s in [0, 1, 2, 3, 4, 128, 129, 130, 131, 132]]

    def fake_get(url, params=None, timeout=None):
        if url.endswith("/explorer"):
            return _response({"rows": []})
        return _response({"players": players})

    with patch("backend.rosters.requests.get", side_effect=fake_get):
        lineup = get_match_lineup(42)

    assert len(lineup) == 10
    assert (128, 1128) in lineup


def test_incomplete_lineup_is_not_cached(ctx):
    with patch("backend.rosters.requests.get", return_value=_response({"rows": []})) as mock_get:
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


def test_series_grouping_splits_on_opponent_and_gap():
    matches = [
        TeamMatch(match_id=5, start_time=NOW, radiant=True, opposing_team_id=1, leagueid=1),
        TeamMatch(match_id=4, start_time=NOW - 3600, radiant=True, opposing_team_id=1, leagueid=1),
        TeamMatch(match_id=3, start_time=NOW - 7200, radiant=True, opposing_team_id=2, leagueid=1),
        TeamMatch(match_id=2, start_time=NOW - 3 * DAY, radiant=True, opposing_team_id=2, leagueid=1),
    ]
    assert [m.match_id for m in _latest_match_per_series(matches, 5)] == [5, 3, 2]
    assert [m.match_id for m in _latest_match_per_series(matches, 2)] == [5, 3]


def test_create_team_stats_uses_recent_lineup(ctx):
    from backend.pro_players import Player
    from backend.rosters import LeagueForm, TeamRoster
    from backend.stats import TeamStats, _create_team_stats

    roster = TeamRoster(
        players=[Player(id=1, name="a"), Player(id=2, name="b")],
        other_players=[Player(id=5, name="coach")],
        standins_count=1,
        core_count=1,
        last_match_time=NOW,
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
        {3: _explorer_rows(RADIANT_PLAYERS, DIRE_PLAYERS)},
    )
    with patch("backend.rosters.requests.get", side_effect=fake.get):
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

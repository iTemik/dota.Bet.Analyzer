"""Tests for the constructors of data objects built from OpenDota and DB rows."""

import pytest

from backend.helpers import ExplorerTeam
from backend.opendota import is_radiant
from backend.rosters import TeamMatch, window_start
from backend.stats import MatchStats


def test_match_stats_from_api_and_won():
    row = {"match_id": 1, "player_slot": 130, "radiant_win": False, "game_mode": 22, "lobby_type": 7, "hero_id": 5}
    match = MatchStats.from_api({**row, "extra": "ignored"})
    assert match.average_rank is None
    assert match.won  # Dire player, Dire won
    assert not MatchStats.from_api({**row, "player_slot": 0}).won


def test_match_stats_from_api_rejects_missing_fields():
    with pytest.raises(ValueError):
        MatchStats.from_api({"match_id": 1})


def test_team_match_from_api_and_db():
    row = {"match_id": "7", "start_time": 100, "leagueid": 3, "radiant": 0, "radiant_win": True}
    match = TeamMatch.from_api(row)
    assert (match.match_id, match.radiant, match.won) == (7, False, False)
    db_row = {**row, "match_id": 7, "radiant_win": 1, "opposing_team_id": None, "duration": None}
    assert TeamMatch.from_db(db_row) == match
    with pytest.raises(KeyError):
        TeamMatch.from_api({"match_id": 7})


def test_explorer_team_from_response():
    payload = {"command": "SELECT", "rows": [{"team_id": 1, "name": "A", "tag": "a", "rating": "x", "delta": 2.5}]}
    team = ExplorerTeam.from_response(payload)
    assert (team.team_id, team.name, team.tag, team.rating, team.delta) == (1, "A", "a", None, 2.5)
    with pytest.raises(ValueError, match="No rows"):
        ExplorerTeam.from_response({"command": "SELECT", "rows": []})


def test_small_helpers():
    assert is_radiant(127) and not is_radiant(128)
    assert window_start(2, 3 * 86400) == 86400

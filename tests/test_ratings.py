"""Tests for the rating change estimate over a window (backend.ratings)."""

from unittest.mock import patch

import pytest

from backend.pro_players import get_d2ba_db
from backend.ratings import (
    RATING_K,
    estimate_rating_change,
    expected_score,
    window_rating_change,
)
from backend.rosters import TeamMatch

NOW = 1_792_300_000
DAY = 24 * 60 * 60
TEAM_ID = 2576071


def _match(match_id: int, days_ago: float, opponent: int | None, won: bool) -> TeamMatch:
    return TeamMatch(
        match_id=match_id,
        start_time=int(NOW - days_ago * DAY),
        radiant=True,
        radiant_win=won,
        opposing_team_id=opponent,
    )


def test_expected_score():
    assert expected_score(1000, 1000) == 0.5
    assert expected_score(1100, 1000) == pytest.approx(0.64, abs=0.01)


def test_win_over_equal_team_gives_half_k():
    change = estimate_rating_change(1000 + RATING_K / 2, [_match(1, 1, 7, won=True)], {7: 1000})
    assert change == pytest.approx(RATING_K / 2, abs=0.1)


def test_games_are_worked_back_newest_first():
    """A win and a loss against equal teams roughly cancel out; unknown opponents are skipped."""
    matches = [
        _match(1, 1, 7, won=True),
        _match(2, 2, 8, won=False),
        _match(3, 3, 9, won=True),
        _match(4, 4, None, True),
    ]
    change = estimate_rating_change(1000, matches, {7: 1000, 8: 1000})
    assert change == pytest.approx(0, abs=1)
    assert estimate_rating_change(1000, [_match(1, 1, 9, won=True)], {}) is None


def test_window_rating_change_reads_local_ratings(app):
    with app.app_context():
        db = get_d2ba_db()
        db.executemany("INSERT INTO teams (team_id, name, rating) VALUES (?, ?, ?)", [(7, "a", 1200), (8, "b", 800)])
        db.commit()
        matches = [_match(1, 1, 7, won=True), _match(2, 30, 8, won=False)]  # the second is outside the window
        with patch("backend.ratings.get_team_league_matches", return_value=matches):
            change = window_rating_change(TEAM_ID, 1500, days=20, now=NOW)
            assert window_rating_change(TEAM_ID, None, days=20, now=NOW) is None
    # A win over a team 300 points weaker gives few points
    assert change == pytest.approx(RATING_K * (1 - expected_score(1500, 1200)), abs=0.5)

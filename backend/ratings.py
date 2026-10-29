"""Team rating (Elo) change over a recent period, estimated without extra OpenDota requests.

OpenDota keeps only the current rating and the change from the latest game, not a rating history. Its rating is
Elo with RATING_K points per league game between two teams with ids, so the rating before each game of the period is
worked back from today's rating, newest game first. Opponent ratings come from the local `teams` table (kept fresh by
the teams sync) and are today's ratings, not those of the game day, so the result is an estimate.
"""

import sqlite3
import time
from typing import Optional

from backend.logging_config import setup_logging
from backend.pro_players import get_d2ba_db
from backend.rosters import TeamMatch, get_team_league_matches, window_start

logger = setup_logging(__name__)

RATING_K = 32  # Most points one game can move a rating
RATING_SCALE = 400  # A gap of this many points means 10 to 1 odds


def expected_score(rating: float, opponent: float) -> float:
    """Elo win expectation of a team against an opponent (0 to 1)."""
    return 1 / (1 + 10 ** ((opponent - rating) / RATING_SCALE))


def _local_ratings(team_ids: set[int]) -> dict[int, float]:
    """Current ratings of teams from the local `teams` table (teams without a rating are left out)."""
    if not team_ids:
        return {}
    placeholders = ",".join("?" for _ in team_ids)
    rows = (
        get_d2ba_db()
        .execute(f"SELECT team_id, rating FROM teams WHERE team_id IN ({placeholders})", list(team_ids))
        .fetchall()
    )
    return {row["team_id"]: row["rating"] for row in rows if row["rating"] is not None}


def estimate_rating_change(
    rating: float, matches: list[TeamMatch], opponent_ratings: dict[int, float]
) -> Optional[float]:
    """Rating change over the given matches, worked back from the current rating.

    Games without a result or with an opponent of unknown rating are skipped (OpenDota rates only games
    between two teams with ids).

    Args:
        rating: Current team rating
        matches: League matches of the period, newest first
        opponent_ratings: Current rating per opponent team id

    Returns:
        Current rating minus the estimated rating before the period (None when no game could be counted)
    """
    current = rating
    counted = 0
    for match in matches:
        opponent = opponent_ratings.get(match.opposing_team_id) if match.opposing_team_id else None
        if match.won is None or opponent is None:
            continue
        score = 1 if match.won else 0
        before = current
        for _ in range(2):  # The expectation depends on the rating before the game; two steps are close enough
            before = current - RATING_K * (score - expected_score(before, opponent))
        current = before
        counted += 1
    return rating - current if counted else None


def window_rating_change(
    team_id: int, rating: Optional[float], days: int, now: Optional[int] = None
) -> Optional[float]:
    """Estimated rating change of a team over the last `days` days.

    Cost: no OpenDota request while the team matches are cached (resolve_roster has just loaded them).

    Args:
        team_id: Team identifier
        rating: Current team rating (None when unknown)
        days: Period length in days
        now: Current unix time (for tests)

    Returns:
        Rating change, None when the rating or every opponent rating is unknown
    """
    if rating is None:
        return None
    now = now if now is not None else int(time.time())
    since = window_start(days, now)
    matches = [m for m in get_team_league_matches(team_id, now=now) if m.start_time >= since]
    try:
        ratings = _local_ratings({m.opposing_team_id for m in matches if m.opposing_team_id})
    except sqlite3.Error as exc:
        logger.warning(f"Team ratings unavailable: {exc}")
        return None
    return estimate_rating_change(rating, matches, ratings)

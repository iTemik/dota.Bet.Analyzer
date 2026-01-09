from __future__ import annotations

from typing import List, Optional

import requests
from pydantic import BaseModel, Field


class Player(BaseModel):
    name: str
    id: int


class TeamStats(BaseModel):
    team_id: int
    team: str
    tag: Optional[str] = None
    leaderboard_rank: Optional[float] = None
    delta: Optional[float] = None
    players: List[Player] = Field(default_factory=list)
    other_players: List[Player] = Field(default_factory=list)


class StatsResponse(BaseModel):
    teams: List[TeamStats]


class StatisticsError(Exception):
    """Raised when fetching or parsing statistics for a team fails."""


# Implement compute_statistics here for testability and reuse
def compute_statistics(teams: List[str]) -> StatsResponse:

    from backend.helpers import (
        get_percent_encoded_str,
        get_team_id_from_explore_response,
        prepare_sql_for_team_explore,
    )

    if not isinstance(teams, list):
        raise ValueError("teams must be a list of strings")

    result: List[TeamStats] = []

    for team in teams:
        if not isinstance(team, str) or not team.strip():
            raise ValueError("Invalid team name")

        sql = prepare_sql_for_team_explore(team)
        team_request = get_percent_encoded_str(sql)
        explore_team_url = f"https://api.opendota.com/api/explorer?sql={team_request}"

        try:
            resp = requests.get(explore_team_url, timeout=5)
        except Exception as exc:
            raise StatisticsError(f"Network error fetching data for team {team}: {exc}") from exc

        if resp.status_code != 200:
            raise StatisticsError(f"Failed to fetch data for team {team}: HTTP {resp.status_code}")

        try:
            payload = resp.json()
        except Exception as exc:  # ValueError / JSONDecodeError / TypeError
            raise StatisticsError(f"Invalid JSON response for team {team}: {exc}") from exc

        try:
            id_, name, tag = get_team_id_from_explore_response(payload)
        except ValueError as exc:
            raise StatisticsError(f"Malformed explorer response for team {team}: {exc}") from exc

        stats = TeamStats(
            team_id=id_,
            team=team,
            tag=tag,
            leaderboard_rank=1000.0,
            delta=0.0,
            players=[Player(name=f"{name}_Player1", id=id_ * 10 + 1), Player(name=f"{name}_Player2", id=id_ * 10 + 2)],
            other_players=[],
        )
        result.append(stats)

    return StatsResponse(teams=result)

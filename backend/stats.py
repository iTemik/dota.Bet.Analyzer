from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class Player(BaseModel):
    name: str
    id: int


class TeamStats(BaseModel):
    team: str
    team_id: int
    leaderboard_rank: Optional[float] = None
    delta: Optional[float] = None
    players: List[Player] = Field(default_factory=list)
    other_players: List[Player] = Field(default_factory=list)


class StatsResponse(BaseModel):
    teams: List[TeamStats]


# TODO: Example stub implementation: replace with real logic later
def compute_statistics(teams: List[str]) -> StatsResponse:
    result: List[TeamStats] = []
    for i, t in enumerate(teams, start=1):
        team = TeamStats(
            team=t,
            team_id=1000 + i,
            leaderboard_rank=1000.0 + i,
            delta=0.0,
            players=[Player(name=f"Player{i}A", id=100 + i), Player(name=f"Player{i}B", id=200 + i)],
            other_players=[],
        )
        result.append(team)
    return StatsResponse(teams=result)

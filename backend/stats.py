from __future__ import annotations

from typing import List, Optional

import requests
from pydantic import BaseModel, Field


class Player(BaseModel):
    """Represents a Dota 2 player.

    Attributes:
        name: Player name
        id: Unique player ID
    """

    name: str
    id: int


class TeamStats(BaseModel):
    """Statistics and information for a Dota 2 team.

    Attributes:
        team_id: Unique team identifier (None if error occurred)
        team: Team name
        tag: Team tag/abbreviation
        leaderboard_rank: Team's leaderboard ranking
        delta: Recent rating change
        players: List of active team players
        other_players: List of inactive/substitute players
        error_code: Error code if team data fetch failed (e.g., NETWORK_ERROR, HTTP_ERROR)
        error_message: Detailed error message if error_code is set
    """

    team_id: Optional[int] = None
    team: str
    tag: Optional[str] = None
    leaderboard_rank: Optional[float] = None
    delta: Optional[float] = None
    players: List[Player] = Field(default_factory=list)
    other_players: List[Player] = Field(default_factory=list)
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class StatsResponse(BaseModel):
    """Response containing statistics for multiple teams.

    Attributes:
        teams: List of team statistics (includes both successful and error results)
    """

    teams: List[TeamStats]


class StatisticsError(Exception):
    """Raised when fetching or parsing statistics for a team fails."""


# Implement compute_statistics here for testability and reuse
def compute_statistics(teams: List[str]) -> StatsResponse:
    """Fetch and compute statistics for multiple Dota 2 teams.

    This function queries the OpenDota API to retrieve team information and statistics.
    Errors are handled gracefully - if a team's data cannot be fetched, the response
    will include that team with error_code and error_message fields populated.

    Args:
        teams: List of team names or tags to fetch statistics for

    Returns:
        StatsResponse containing a list of TeamStats objects. Each TeamStats may
        represent either:
        - Successful fetch: team_id, players, and other data populated
        - Failed fetch: error_code and error_message populated

    Raises:
        ValueError: If teams is not a list

    Error Codes:
        - INVALID_TEAM_NAME: Team name is empty or invalid
        - NETWORK_ERROR: Network/connection error occurred
        - HTTP_ERROR: Non-200 HTTP response from API
        - JSON_DECODE_ERROR: Response is not valid JSON
        - RESPONSE_PARSE_ERROR: Response JSON structure is malformed
        - UNEXPECTED_ERROR: Any other unexpected error
    """
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
            result.append(
                TeamStats(
                    team=team if isinstance(team, str) else str(team),
                    error_code="INVALID_TEAM_NAME",
                    error_message="Invalid team name",
                )
            )
            continue

        try:
            sql = prepare_sql_for_team_explore(team)
            team_request = get_percent_encoded_str(sql)
            explore_team_url = f"https://api.opendota.com/api/explorer?sql={team_request}"

            try:
                resp = requests.get(explore_team_url, timeout=5)
            except Exception as exc:
                result.append(
                    TeamStats(
                        team=team,
                        error_code="NETWORK_ERROR",
                        error_message=f"Network error fetching data: {exc}",
                    )
                )
                continue

            if resp.status_code != 200:
                result.append(
                    TeamStats(
                        team=team,
                        error_code="HTTP_ERROR",
                        error_message=f"HTTP {resp.status_code}",
                    )
                )
                continue

            try:
                payload = resp.json()
            except Exception as exc:
                result.append(
                    TeamStats(
                        team=team,
                        error_code="JSON_DECODE_ERROR",
                        error_message=f"Invalid JSON response: {exc}",
                    )
                )
                continue

            try:
                team_id, team_name, tag = get_team_id_from_explore_response(payload)
            except ValueError as exc:
                result.append(
                    TeamStats(
                        team=team,
                        error_code="RESPONSE_PARSE_ERROR",
                        error_message=f"Malformed response: {exc}",
                    )
                )
                continue

            stats = TeamStats(
                team_id=team_id,
                team=team_name,
                tag=tag,
                leaderboard_rank=0.0,
                delta=0.0,
                players=[],
                other_players=[],
            )
            result.append(stats)

        except Exception as exc:
            # Catch-all for any unexpected errors
            result.append(
                TeamStats(
                    team=team,
                    error_code="UNEXPECTED_ERROR",
                    error_message=f"Unexpected error: {exc}",
                )
            )

    return StatsResponse(teams=result)

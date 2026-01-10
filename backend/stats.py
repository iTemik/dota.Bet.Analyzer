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
        rating: Team's Elo ranking
        delta: Recent rating change
        logo_url: URL to team's logo image
        players: List of active team players
        other_players: List of inactive/substitute players
        error_code: Error code if team data fetch failed (e.g., NETWORK_ERROR, HTTP_ERROR)
        error_message: Detailed error message if error_code is set
    """

    team_id: Optional[int] = None
    team: str
    tag: Optional[str] = None
    rating: Optional[float] = None
    delta: Optional[float] = None
    logo_url: Optional[str] = None
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


def _safe_get_json(url: str, timeout: int = 5) -> tuple[Optional[dict], Optional[tuple[str, str]]]:
    """Safely perform GET request and parse JSON response.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds

    Returns:
        Tuple of (json_data, error) where:
        - json_data is the parsed JSON response (None if error)
        - error is (error_code, error_message) tuple (None if success)
    """
    try:
        resp = requests.get(url, timeout=timeout)
    except Exception as exc:
        return None, ("NETWORK_ERROR", f"Network error fetching data: {exc}")

    if resp.status_code != 200:
        return None, ("HTTP_ERROR", f"HTTP {resp.status_code}")

    try:
        payload = resp.json()
        # print(f"Url: {url} Payload: {payload}")
        return payload, None
    except Exception as exc:
        return None, ("JSON_DECODE_ERROR", f"Invalid JSON response: {exc}")


def _fetch_team_info(team: str) -> tuple[Optional[tuple[int, str, str]], Optional[tuple[str, str]]]:
    """Fetch team ID, name, and tag from OpenDota explorer API.

    Args:
        team: Team name or tag to search for

    Returns:
        Tuple of (team_info, error) where:
        - team_info is (team_id, team_name, tag) tuple (None if error)
        - error is (error_code, error_message) tuple (None if success)
    """
    from backend.helpers import (
        get_percent_encoded_str,
        get_team_id_from_explore_response,
        prepare_sql_for_team_explore,
    )

    sql = prepare_sql_for_team_explore(team)
    team_request = get_percent_encoded_str(sql)
    explore_team_url = f"https://api.opendota.com/api/explorer?sql={team_request}"

    payload, error = _safe_get_json(explore_team_url)
    if error:
        return None, error

    assert payload is not None

    try:
        team_id, team_name, tag = get_team_id_from_explore_response(payload)
        return (team_id, team_name, tag), None
    except ValueError as exc:
        return None, ("RESPONSE_PARSE_ERROR", f"Malformed response: {exc}")


def _fetch_team_stats(team_id: int) -> tuple[Optional[dict], Optional[tuple[str, str]]]:
    """Fetch team statistics from OpenDota teams API.

    Args:
        team_id: Team ID to fetch statistics for

    Returns:
        Tuple of (stats_data, error) where:
        - stats_data is dict with team stats (None if error)
        - error is (error_code, error_message) tuple (None if success)
    """
    team_stats_url = f"https://api.opendota.com/api/teams/{team_id}"
    return _safe_get_json(team_stats_url)


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
            # Fetch team info from explorer API
            team_info, error = _fetch_team_info(team)
            if error:
                error_code, error_message = error
                result.append(TeamStats(team=team, error_code=error_code, error_message=error_message))
                continue

            if team_info is None:
                continue

            team_id, team_name, tag = team_info

            # Fetch team statistics
            stats_data, error = _fetch_team_stats(team_id)
            if error:
                error_code, error_message = error
                result.append(TeamStats(team=team, error_code=error_code, error_message=error_message))
                continue

            if stats_data is None:
                continue

            stats = TeamStats(
                team_id=team_id,
                team=team_name,
                tag=tag,
                rating=stats_data.get("rating"),
                delta=stats_data.get("delta"),
                logo_url=stats_data.get("logo_url"),
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

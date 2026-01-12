from __future__ import annotations

from typing import List, Optional

import requests
from pydantic import BaseModel, Field

from backend.pro_players import get_players_by_team, Player


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


class MatchStats(BaseModel):
    """Statistics for a single Dota 2 match.

    Attributes:
        match_id: Unique match identifier
        player_slot: Player slot number (0-127)
        radiant_win: Whether the radiant team won
        game_mode: Game mode ID
        lobby_type: Lobby type ID
        hero_id: Hero ID played in the match
        average_rank: Average rank tier of the match
    """

    match_id: int
    player_slot: int
    radiant_win: bool
    game_mode: int
    lobby_type: int
    hero_id: int
    average_rank: Optional[int] = None


class StatsResponse(BaseModel):
    """Response containing statistics for multiple teams.

    Attributes:
        teams: List of team statistics (includes both successful and error results)
    """

    teams: List[TeamStats]


class MatchesSummary(BaseModel):
    """Summary statistics for a collection of matches.

    Attributes:
        rating_matches: TODO - calculation to be implemented
        tournament_matches: Number of matches in the dataset
        matches_median: TODO - calculation to be implemented
        matches_avg: TODO - calculation to be implemented
        win_percentage: TODO - calculation to be implemented
    """

    rating_matches: Optional[float] = None
    tournament_matches: int
    matches_median: Optional[float] = None
    matches_avg: Optional[float] = None
    win_percentage: Optional[float] = None


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


def _fetch_team_info_from_explorer(
    team: str,
) -> tuple[Optional[tuple[int, str, str, float | None, float | None]], Optional[tuple[str, str]]]:
    """Fetch team info including rating and delta from OpenDota explorer API.

    Args:
        team: Team name or tag to search for

    Returns:
        Tuple of (team_info, error) where:
        - team_info is (team_id, team_name, tag, rating, delta) tuple (None if error)
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
        team_id, team_name, tag, rating, delta = get_team_id_from_explore_response(payload)
        return (team_id, team_name, tag, rating, delta), None
    except ValueError as exc:
        return None, ("RESPONSE_PARSE_ERROR", f"Malformed response: {exc}")


def _fetch_team_info(team_id: int) -> tuple[Optional[dict], Optional[tuple[str, str]]]:
    """Fetch team statistics from OpenDota teams API.

    Args:
        team_id: Team ID to fetch statistics for

    Returns:
        Tuple of (data, error) where:
        - data is the team information (None if error or not available)
        - error is (error_code, error_message) tuple (None if success)
    """
    team_info_url = f"https://api.opendota.com/api/teams/{team_id}"
    data, error = _safe_get_json(team_info_url)
    
    if error or data is None:
        return None, error
    
    return data, None


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
            # Fetch team info from explorer API (now includes rating and delta)
            team_info1, error = _fetch_team_info_from_explorer(team)
            if error:
                error_code, error_message = error
                result.append(TeamStats(team=team, error_code=error_code, error_message=error_message))
                continue

            if team_info1 is None:
                continue

            team_id, team_name, tag, rating, delta = team_info1
            players = get_players_by_team(team_id=team_id)
            
            # Fetch team logo URL
            team_info2, error = _fetch_team_info(team_id)
            if error:
                error_code, error_message = error
                result.append(TeamStats(team=team, error_code=error_code, error_message=error_message))           

            stats = TeamStats(
                team_id=team_id,
                team=team_name,
                tag=tag,
                rating=rating,
                delta=delta,
                logo_url=team_info2.get("logo_url") if team_info2 else None,
                players=players,
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


def get_matches(account_id: int, days: int = 90) -> list[MatchStats]:
    """Fetch matches for a player from OpenDota API.

    Args:
        account_id: Player account ID
        days: Number of days of match history to fetch (default 90)

    Returns:
        List of MatchStats objects representing the player's recent matches

    Raises:
        ValueError: If account_id is invalid
        requests.RequestException: If API request fails
    """
    if not isinstance(account_id, int) or account_id < 0:
        raise ValueError("account_id must be a non-negative integer")

    url = f"https://api.opendota.com/api/players/{account_id}/matches?date={days}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        try:
            data = response.json()
        except (ValueError, requests.JSONDecodeError) as exc:
            raise requests.RequestException(f"Failed to fetch matches for account {account_id}: Invalid JSON - {exc}")

        if not isinstance(data, list):
            return []

        matches = []
        for match_data in data:
            try:
                match = MatchStats(
                    match_id=match_data.get("match_id"),
                    player_slot=match_data.get("player_slot"),
                    radiant_win=match_data.get("radiant_win"),
                    game_mode=match_data.get("game_mode"),
                    lobby_type=match_data.get("lobby_type"),
                    hero_id=match_data.get("hero_id"),
                    average_rank=match_data.get("average_rank"),
                )
                matches.append(match)
            except Exception:
                # Skip malformed match entries
                continue

        return matches

    except requests.RequestException as exc:
        raise requests.RequestException(f"Failed to fetch matches for account {account_id}: {exc}")


def get_team_matches_summary(matches: list[MatchStats]) -> MatchesSummary:
    """Generate summary statistics from a list of matches.

    Args:
        matches: List of MatchStats objects to summarize

    Returns:
        MatchesSummary containing:
        - tournament_matches: Count of matches
        - rating_matches, matches_median, matches_avg, win_percentage: TODO calculations
    """
    return MatchesSummary(
        rating_matches=None,  # TODO: Implement calculation
        tournament_matches=len(matches),
        matches_median=None,  # TODO: Implement calculation
        matches_avg=None,  # TODO: Implement calculation
        win_percentage=None,  # TODO: Implement calculation
    )


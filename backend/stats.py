from __future__ import annotations

import statistics
import time
from typing import List, Optional

import requests
from pydantic import BaseModel, Field

from backend.logging_config import setup_logging
from backend.pro_players import Player, get_players_by_team

LOBBY_TYPE_RATING = [0, 4, 5, 6, 7, 9, 22]
LOBBY_TYPE_TOURNAMENT = [1, 2]
GAME_MODE_RATING = [1, 3, 4, 22]
GAME_MODE_TOURNAMENT = [2]

# Setup logger
logger = setup_logging(__name__)


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
        task_id: Celery task ID for fetching player match statistics (None if not initiated)
        error_code: Error code if team data fetch failed (e.g., NETWORK_ERROR, HTTP_ERROR)
        message: Detailed error message if error_code is set
        details: Additional error context (e.g., API URLs that caused the error)
    """

    team_id: Optional[int] = None
    team: str
    tag: Optional[str] = None
    rating: Optional[float] = None
    delta: Optional[float] = None
    logo_url: Optional[str] = None
    players: List[Player] = Field(default_factory=list)
    other_players: List[Player] = Field(default_factory=list)
    task_id: Optional[str] = None
    error_code: Optional[str] = None
    message: Optional[str] = None
    details: Optional[dict] = None


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
        rating_matches: Number of rating matches
        tournament_matches: Number of tournament matches
        other_matches: Number of all other matches
        matches_median: Median number of matches per player
        matches_avg: Average number of matches per player
        win_percentage: TODO - calculation to be implemented
    """

    rating_matches: int = 0
    tournament_matches: int = 0
    other_matches: int = 0
    matches_median: Optional[float] = None
    matches_avg: Optional[float] = None
    win_percentage: Optional[float] = None
    avg_rank: Optional[float] = None
    bad_rank_players: Optional[int] = None


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
        - error is (error_code, message) tuple (None if success)
    """
    try:
        resp = requests.get(url, timeout=timeout)
    except Exception as exc:
        return None, ("NETWORK_ERROR", f"Network error fetching data: {exc}")

    if resp.status_code != 200:
        return None, ("HTTP_ERROR", f"HTTP {resp.status_code} from API")

    try:
        payload = resp.json()
        # print(f"Url: {url} Payload: {payload}")
        return payload, None
    except Exception as exc:
        return None, ("JSON_DECODE_ERROR", f"Invalid JSON response: {exc}")


def _fetch_team_info_from_explorer(
    team: str,
) -> tuple[Optional[tuple[int, str, str, float | None, float | None]], Optional[tuple[str, str, dict]]]:
    """Fetch team info including rating and delta from OpenDota explorer API.

    Args:
        team: Team name or tag to search for

    Returns:
        Tuple of (team_info, error) where:
        - team_info is (team_id, team_name, tag, rating, delta) tuple (None if error)
        - error is (error_code, message, details) tuple (None if success)
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
        error_code, message = error
        return None, (error_code, message, {"url": explore_team_url})

    assert payload is not None

    try:
        team_id, team_name, tag, rating, delta = get_team_id_from_explore_response(payload)
        return (team_id, team_name, tag, rating, delta), None
    except ValueError as exc:
        return None, ("RESPONSE_PARSE_ERROR", f"Malformed response: {exc}", {"url": explore_team_url})


def _fetch_team_info(team_id: int) -> tuple[Optional[dict], Optional[tuple[str, str, dict]]]:
    """Fetch team statistics from OpenDota teams API.

    Args:
        team_id: Team ID to fetch statistics for

    Returns:
        Tuple of (data, error) where:
        - data is the team information (None if error or not available)
        - error is (error_code, message, details) tuple (None if success)
    """
    team_info_url = f"https://api.opendota.com/api/teams/{team_id}"
    data, error = _safe_get_json(team_info_url)

    if error:
        error_code, message = error
        return None, (error_code, message, {"url": team_info_url})

    return data, None


def _fetch_team_stats(team_id: int) -> tuple[Optional[dict], Optional[tuple[str, str, dict]]]:
    """Fetch team logo URL from OpenDota teams API.

    Args:
        team_id: Team ID to fetch logo for

    Returns:
        Tuple of (stats_data, error) where:
        - stats_data is json with team stats (None if error)
        - error is (error_code, message, details) tuple (None if success)
    """
    stats_data, error = _fetch_team_info(team_id)

    if error or stats_data is None:
        return None, error

    return stats_data, None


# Implement compute_statistics here for testability and reuse
def compute_statistics(teams: List[str]) -> StatsResponse:
    """Fetch and compute statistics for multiple Dota 2 teams.

    This function queries the OpenDota API to retrieve team information and statistics.
    For each team with players, it initiates a Celery task to fetch player match statistics.
    Errors are handled gracefully - if a team's data cannot be fetched, the response
    will include that team with error_code and message fields populated.

    Args:
        teams: List of team names or tags to fetch statistics for

    Returns:
        StatsResponse containing a list of TeamStats objects. Each TeamStats may
        represent either:
        - Successful fetch: team_id, players, task_id, and other data populated
        - Failed fetch: error_code and message populated

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
    # Import here to avoid circular imports
    from backend.dota_bet_analyzer import players_statistics_task

    if not isinstance(teams, list):
        raise ValueError("teams must be a list of strings")

    result: List[TeamStats] = []

    for team in teams:
        if not isinstance(team, str) or not team.strip():
            result.append(
                TeamStats(
                    team=team if isinstance(team, str) else str(team),
                    error_code="INVALID_TEAM_NAME",
                    message="Invalid team name",
                )
            )
            continue

        try:
            # Fetch team info from explorer API (now includes rating and delta)
            team_info1, error = _fetch_team_info_from_explorer(team)
            if error:
                error_code, message, details = error
                result.append(TeamStats(team=team, error_code=error_code, message=message, details=details))
                continue

            if team_info1 is None:
                continue

            team_id, team_name, tag, rating, delta = team_info1
            pro_players, other_players = get_players_by_team(team_id=team_id)

            # Fetch team logo URL
            team_info2, error = _fetch_team_stats(team_id)
            if error:
                error_code, message, details = error
                result.append(TeamStats(team=team, error_code=error_code, message=message, details=details))
                continue

            # Initiate Celery task for player match statistics if players exist
            task_id = None
            if pro_players:
                account_ids = [player.id for player in pro_players]
                task_id = f"task_{team_name}_{int(time.time())}"
                players_statistics_task.delay(task_id=task_id, accounts=account_ids)

            stats = TeamStats(
                team_id=team_id,
                team=team_name,
                tag=tag,
                rating=rating,
                delta=delta,
                logo_url=team_info2.get("logo_url") if team_info2 else None,
                players=pro_players,
                other_players=other_players,
                task_id=task_id,
            )
            result.append(stats)

        except Exception as exc:
            # Catch-all for any unexpected errors
            result.append(
                TeamStats(
                    team=team,
                    error_code="UNEXPECTED_ERROR",
                    message=f"Unexpected error: {exc} during compute_statistics for team {team}",
                )
            )

    return StatsResponse(teams=result)


def get_matches(account_id: int, days: int = 20) -> list[MatchStats]:
    """Fetch matches for a player from OpenDota API.

    It's heavy request it may take several minutes to complete.

    Args:
        account_id: Player account ID
        days: Number of days of match history to fetch (default 20)

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
        logger.debug(f"Fetching matches for account {account_id} from URL: {url}")
        response = requests.get(url, timeout=60)
        response.raise_for_status()

        try:
            data = response.json()
        except (ValueError, requests.JSONDecodeError) as exc:
            error_msg = f"Failed to fetch matches for account {account_id}: Invalid JSON - {exc}"
            raise requests.RequestException(error_msg) from exc

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
        raise requests.RequestException(f"Failed to fetch matches for account {account_id}: {exc}") from exc


def get_rank(account_id: int) -> Optional[int]:
    """Fetch player's leaderboard rank from OpenDota API.

    Args:
        account_id: Player's account ID

    Returns:
        Leaderboard rank value (None if not found or error occurred)
    """
    url = f"https://api.opendota.com/api/players/{account_id}"
    data, error = _safe_get_json(url)

    if error:
        error_code, message = error
        logger.debug(f"Failed to fetch rank for account {account_id}: {error_code} - {message}")
        return None

    if data is None:
        return None

    rank = data.get("leaderboard_rank")

    if rank is None:
        logger.debug(f"No leaderboard_rank found for account {account_id}")
        return None

    try:
        return int(rank) if rank else None
    except (ValueError, TypeError):
        logger.warning(f"Invalid rank value for account {account_id}: {rank}")
        return None


def get_team_matches_summary(matches_by_player: list[list[MatchStats]]) -> MatchesSummary:
    """Generate summary statistics from lists of matches per player.

    Args:
        matches_by_player: List of lists, where each inner list contains MatchStats for one player

    Returns:
        MatchesSummary containing categorized match counts:
        - rating_matches: Matches with game_mode in GAME_MODE_RATING and lobby_type in LOBBY_TYPE_RATING
        - tournament_matches: Matches with game_mode in GAME_MODE_TOURNAMENT and lobby_type in LOBBY_TYPE_TOURNAMENT
        - other_matches: All remaining matches
        - matches_avg: Average number of matches per player
        - matches_median: Median number of matches per player
    """
    rating_matches = 0
    tournament_matches = 0
    other_matches = 0
    total_matches = 0
    player_match_counts = []
    wins = 0

    # TODO: exclude coaches and strange players from the statistics calculation.
    # These players should not impact on average matches.

    # Iterate through all players' matches and categorize them
    for player_matches in matches_by_player:
        player_match_count = len(player_matches)
        player_match_counts.append(player_match_count)

        for match in player_matches:
            total_matches += 1
            if match.game_mode in GAME_MODE_RATING and match.lobby_type in LOBBY_TYPE_RATING:
                rating_matches += 1
            elif match.game_mode in GAME_MODE_TOURNAMENT and match.lobby_type in LOBBY_TYPE_TOURNAMENT:
                tournament_matches += 1
            else:
                other_matches += 1

            if (match.player_slot < 128 and match.radiant_win) or (match.player_slot >= 128 and not match.radiant_win):
                wins += 1

    # Calculate average matches per player
    num_players = len(matches_by_player)
    matches_avg = total_matches / num_players if num_players > 0 else 0.0

    # Calculate median matches per player
    matches_median = statistics.median(player_match_counts) if player_match_counts else 0.0

    return MatchesSummary(
        rating_matches=rating_matches,
        tournament_matches=tournament_matches,
        other_matches=other_matches,
        matches_median=matches_median,
        matches_avg=matches_avg,
        win_percentage=100 * wins / total_matches if total_matches > 0 else 0.0,
    )

from __future__ import annotations

import statistics
import time
from typing import List, Optional

import requests
from pydantic import BaseModel, Field

from backend.helpers import ApiError, Errors
from backend.logging_config import setup_logging
from backend.opendota import OPENDOTA_API, OpenDotaError, WaitCallback, get_json
from backend.pro_players import Player, get_players_by_team
from backend.rosters import LeagueForm, TeamRoster, resolve_roster

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
        players: Main roster; player statistics are calculated from it
        other_players: Everyone else: players who played league games for the team in the window (with `games`),
            then players OpenDota lists on the team who did not (`games` 0)
        roster_source: Where `players` came from: "recent_matches" (players with the most league games in the
            window) or "pro_players" (OpenDota team membership, may be stale)
        roster_games: Number of league games in the window the roster was counted from
        standins_count: Stand-ins: players who played in the window but are outside the core (below 75%, or 50%,
            of the games)
        roster_last_match_time: Start time of the latest league match played by most of the roster (unix seconds)
        latest_match_time: Start time of the team's latest league match (unix seconds)
        latest_match_standins: Players of the latest league match who are not in the core
        roster_state: "stable" (only the core played), "standins" (a clear core plus stand-ins) or "new_team"
            (no clear core); None when unknown
        league_form: League results over the roster period (pubs excluded)
        task_id: Celery task ID for fetching player match statistics (None if not initiated)
        error: Error information if team data fetch failed
    """

    team_id: Optional[int] = None
    team: Optional[str] = None
    tag: Optional[str] = None
    rating: Optional[float] = None
    delta: Optional[float] = None
    logo_url: Optional[str] = None
    players: List[Player] = Field(default_factory=list)
    other_players: List[Player] = Field(default_factory=list)
    roster_source: Optional[str] = None
    roster_games: Optional[int] = None
    standins_count: int = 0
    roster_last_match_time: Optional[int] = None
    latest_match_time: Optional[int] = None
    latest_match_standins: Optional[int] = None
    roster_state: Optional[str] = None
    league_form: Optional[LeagueForm] = None
    task_id: Optional[str] = None
    error: Optional[ApiError] = None


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
        tournament_matches: Number of lobby matches (league games and scrims, OpenDota can't tell them apart here)
        other_matches: Number of all other matches
        matches_median: Median number of matches per player
        matches_avg: Average number of matches per player
        win_percentage: Win percentage across all matches
        rating_win_percentage: Win percentage in rating (pub) matches only
        tournament_win_percentage: Win percentage in lobby matches only
    """

    rating_matches: int = 0
    tournament_matches: int = 0
    other_matches: int = 0
    matches_median: Optional[float] = None
    matches_avg: Optional[float] = None
    win_percentage: Optional[float] = None
    rating_win_percentage: Optional[float] = None
    tournament_win_percentage: Optional[float] = None
    avg_rank: Optional[float] = None
    bad_rank_players: Optional[int] = None


class StatisticsError(Exception):
    """Raised when fetching or parsing statistics for a team fails."""


def _safe_get_json(
    url: str, timeout: int = 5, on_wait: Optional[WaitCallback] = None
) -> tuple[Optional[dict], Optional[ApiError]]:
    """Safely perform GET request and parse JSON response.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        on_wait: Called with the delay in seconds when the request is postponed by the OpenDota limits

    Returns:
        Tuple of (json_data, error) where:
        - json_data is the parsed JSON response (None if error)
        - error is an ApiError instance (None if success)
    """
    try:
        return get_json(url, timeout=timeout, on_wait=on_wait), None
    except OpenDotaError as exc:
        return None, ApiError(status=exc.status, code=exc.code, message=exc.message)


def _team_error(team_str: Optional[str], team_id: Optional[int], error: ApiError) -> TeamStats:
    """TeamStats for a team that could not be fetched.

    Args:
        team_str: Requested team name
        team_id: Requested team ID
        error: What went wrong

    Returns:
        TeamStats with only the request and the error set
    """
    return TeamStats(team=team_str, team_id=team_id, error=error)


def _fetch_team_from_explorer_api(
    team_str: str | None = None,
    team_id: int | None = None,
) -> TeamStats:
    """Fetch team info including rating, delta, and logo from OpenDota APIs.

    Args:
        team_str: Team name or tag to search for (mutually exclusive with team_id)
        team_id: Team ID to search for (mutually exclusive with team_str)

    Returns:
        TeamStats instance with all fetched data and empty players lists (or error if fetch failed)
    """
    from backend.helpers import (
        build_explorer_query,
        get_percent_encoded_str,
        get_team_id_from_explore_response,
    )

    # Validate input parameters
    if team_str is not None and (not isinstance(team_str, str) or not team_str.strip()):
        return _team_error(team_str, team_id, ApiError.of(Errors.INVALID_TEAM_NAME, 400, team=team_str))

    if team_id is not None and (not isinstance(team_id, int) or team_id < 0):
        return _team_error(team_str, team_id, ApiError.of(Errors.INVALID_TEAM_ID, 400, team_id=team_id))

    try:
        sql = build_explorer_query(team=team_str, team_id=team_id)
    except ValueError as e:
        return _team_error(
            team_str,
            team_id,
            ApiError(
                status=400,
                code="INVALID_PARAMETER",
                message=str(e),
                details={"team": team_str, "team_id": team_id},
            ),
        )

    team_request = get_percent_encoded_str(sql)
    explore_team_url = f"{OPENDOTA_API}/explorer?sql={team_request}"

    payload, error = _safe_get_json(explore_team_url)
    if error:
        error.details = {"url": explore_team_url}
        return _team_error(team_str, team_id, error)

    assert payload is not None

    try:
        team_id_result, team_name, tag, rating, delta = get_team_id_from_explore_response(payload)
    except ValueError as exc:
        return _team_error(
            team_str,
            team_id,
            ApiError(
                status=502,
                code="RESPONSE_PARSE_ERROR",
                message=f"Malformed response: {exc}",
                details={"url": explore_team_url},
            ),
        )

    # Fetch team logo URL
    team_info, error = _fetch_team_info(team_id_result)
    if error:
        return TeamStats(
            team_id=team_id_result,
            team=team_name,
            tag=tag,
            rating=rating,
            delta=delta,
            error=error,
        )

    logo_url = team_info.get("logo_url") if team_info else None

    return TeamStats(
        team_id=team_id_result,
        team=team_name,
        tag=tag,
        rating=rating,
        delta=delta,
        logo_url=logo_url,
    )


def _fetch_team_info(team_id: int) -> tuple[Optional[dict], Optional[ApiError]]:
    """Fetch team statistics from OpenDota teams API.

    Args:
        team_id: Team ID to fetch statistics for

    Returns:
        Tuple of (data, error) where:
        - data is the team information (None if error or not available)
        - error is an ApiError instance (None if success)
    """
    team_info_url = f"{OPENDOTA_API}/teams/{team_id}"
    data, error = _safe_get_json(team_info_url)

    if error:
        error.details = {"url": team_info_url}
        return None, error

    return data, None


def _resolve_roster_safe(team_id: Optional[int], days: int) -> TeamRoster:
    """Resolve the roster from recent league matches, never raising.

    Args:
        team_id: Team identifier
        days: Roster window in days (same as the player match history window)

    Returns:
        TeamRoster (empty when team_id is missing or resolution failed)
    """
    if not team_id:
        return TeamRoster()
    try:
        return resolve_roster(team_id, days=days)
    except Exception as exc:
        logger.warning(f"Failed to resolve roster for team {team_id}: {exc}")
        return TeamRoster()


def _create_team_stats(
    team_stats: TeamStats,
    players_statistics_task,
    days: int = 20,
) -> TeamStats:
    """Populate TeamStats with player data and task initialization.

    Takes the roster from the team's recent league matches (falls back to the OpenDota team
    membership in pro_players when there was none recently) and initiates background task
    to fetch player match statistics. This is the main source of accounts
    when team statistics are requested (indirect path).

    Args:
        team_stats: TeamStats instance with team info (empty player lists)
        players_statistics_task: Celery task for player statistics
        days: Roster window and match history window in days

    Returns:
        TeamStats object with players and task_id populated
    """
    pro_players, other_players = get_players_by_team(team_id=team_stats.team_id)
    roster = _resolve_roster_safe(team_stats.team_id, days)

    if roster.players:
        # Main roster from recent league matches; team members from pro_players who did not play are kept last
        played = {p.id for p in [*roster.players, *roster.other_players]}
        listed = [p.model_copy(update={"games": 0}) for p in [*pro_players, *other_players] if p.id not in played]
        team_stats.players = roster.players
        team_stats.other_players = [*roster.other_players, *listed]
        team_stats.roster_source = "recent_matches"
        team_stats.roster_games = roster.games_checked
        team_stats.standins_count = roster.standins_count
        team_stats.roster_last_match_time = roster.last_match_time
        team_stats.latest_match_time = roster.latest_match_time
        team_stats.latest_match_standins = roster.latest_match_standins
        team_stats.roster_state = roster.roster_state
    else:
        team_stats.players = pro_players
        team_stats.other_players = other_players
        team_stats.roster_source = "pro_players"
    team_stats.league_form = roster.league_form

    # Initiate Celery task for player match statistics if players exist
    task_id = None
    if team_stats.players:
        account_ids = [player.id for player in team_stats.players]
        task_id = f"task_{team_stats.team_id}_{int(time.time())}"
        players_statistics_task.delay(task_id=task_id, accounts=account_ids, days=days)

    team_stats.task_id = task_id

    return team_stats


def _process_single_team(
    team_str: str | None = None,
    team_id: int | None = None,
    players_statistics_task=None,
    days: int = 20,
) -> TeamStats:
    """Process a single team item and return TeamStats with players populated.

    Args:
        team_str: Team name to search for (mutually exclusive with team_id)
        team_id: Team ID to search for (mutually exclusive with team_str)
        players_statistics_task: Celery task for player statistics

    Returns:
        TeamStats object with all data populated, or error if fetch failed
    """
    try:
        team_stats = _fetch_team_from_explorer_api(team_str=team_str, team_id=team_id)
        if team_stats.error:
            return team_stats

        # Populate player data and create final team stats
        return _create_team_stats(
            team_stats=team_stats,
            players_statistics_task=players_statistics_task,
            days=days,
        )

    except Exception as exc:
        return _team_error(team_str, team_id, ApiError.of(Errors.UNEXPECTED_ERROR, 500, exception=str(exc)))


# Implement compute_statistics here for testability and reuse
def compute_statistics(
    teams: Optional[List[str]] = None,
    team_ids: Optional[List[int]] = None,
    days: int = 20,
) -> StatsResponse:
    """Fetch and compute statistics for multiple Dota 2 teams.

    This function queries the OpenDota API to retrieve team information and statistics
    by team names and/or team IDs. For each team with players, it initiates
    a Celery task to fetch player match statistics. Errors are handled gracefully -
    if a team's data cannot be fetched, the response will include that team with
    error information populated.

    Args:
        teams: List of team names or tags to fetch statistics for (optional)
        team_ids: List of team IDs to fetch statistics for (optional)
        days: Window in days for the roster (recent league matches) and player match history

    Returns:
        StatsResponse containing a list of TeamStats objects. Each TeamStats may
        represent either:
        - Successful fetch: team_id, players, task_id, and other data populated
        - Failed fetch: error field populated

    Raises:
        ValueError: If neither parameter is provided

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

    # Validate parameters - at least one must be provided
    if (teams is None and team_ids is None) or (not teams and not team_ids):
        raise ValueError("Either 'teams' or 'team_ids' must be provided")

    if teams is not None and not isinstance(teams, list):
        raise ValueError("teams must be a list")
    if team_ids is not None and not isinstance(team_ids, list):
        raise ValueError("team_ids must be a list")

    result: List[TeamStats] = []

    # Process teams by name
    if teams:
        for team_str in teams:
            result.append(
                _process_single_team(team_str=team_str, players_statistics_task=players_statistics_task, days=days)
            )

    # Process teams by ID
    if team_ids:
        for team_id in team_ids:
            result.append(
                _process_single_team(team_id=team_id, players_statistics_task=players_statistics_task, days=days)
            )

    return StatsResponse(teams=result)


def get_matches(account_id: int, days: int = 20, on_wait: Optional[WaitCallback] = None) -> list[MatchStats]:
    """Fetch matches for a player from OpenDota API.

    It's heavy request it may take several minutes to complete.

    Args:
        account_id: Player account ID
        days: Number of days of match history to fetch (default 20)
        on_wait: Called with the delay in seconds when the request is postponed by the OpenDota limits

    Returns:
        List of MatchStats objects representing the player's recent matches

    Raises:
        ValueError: If account_id is invalid
        requests.RequestException: If API request fails
    """
    if not isinstance(account_id, int) or account_id < 0:
        raise ValueError("account_id must be a non-negative integer")

    url = f"{OPENDOTA_API}/players/{account_id}/matches?date={days}"
    logger.debug(f"Fetching matches for account {account_id} from URL: {url}")
    try:
        data = get_json(url, timeout=60, on_wait=on_wait)
    except OpenDotaError as exc:
        raise requests.RequestException(f"Failed to fetch matches for account {account_id}: {exc}") from exc

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


def get_rank(account_id: int, on_wait: Optional[WaitCallback] = None) -> Optional[int]:
    """Fetch player's leaderboard rank from OpenDota API.

    Args:
        account_id: Player's account ID
        on_wait: Called with the delay in seconds when the request is postponed by the OpenDota limits

    Returns:
        Leaderboard rank value (None if not found or error occurred)
    """
    url = f"{OPENDOTA_API}/players/{account_id}"
    data, error = _safe_get_json(url, on_wait=on_wait)

    if error:
        logger.debug(f"Failed to fetch rank for account {account_id}: {error.code} - {error.message}")
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
    rating_wins = 0
    tournament_wins = 0

    # TODO: exclude coaches and strange players from the statistics calculation.
    # These players should not impact on average matches.

    # Iterate through all players' matches and categorize them
    for player_matches in matches_by_player:
        player_match_count = len(player_matches)
        player_match_counts.append(player_match_count)

        for match in player_matches:
            total_matches += 1
            won = (match.player_slot < 128 and match.radiant_win) or (
                match.player_slot >= 128 and not match.radiant_win
            )
            if won:
                wins += 1

            if match.game_mode in GAME_MODE_RATING and match.lobby_type in LOBBY_TYPE_RATING:
                rating_matches += 1
                rating_wins += int(won)
            elif match.game_mode in GAME_MODE_TOURNAMENT and match.lobby_type in LOBBY_TYPE_TOURNAMENT:
                tournament_matches += 1
                tournament_wins += int(won)
            else:
                other_matches += 1

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
        rating_win_percentage=100 * rating_wins / rating_matches if rating_matches > 0 else None,
        tournament_win_percentage=100 * tournament_wins / tournament_matches if tournament_matches > 0 else None,
    )

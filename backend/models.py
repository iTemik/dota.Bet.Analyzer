"""Pydantic data models shared by the statistics, roster and pro players modules.

Kept in one module with no backend imports except helpers and opendota, so any module can import them
without import cycles.
"""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field

from backend.helpers import ApiError
from backend.opendota import is_radiant


class Player(BaseModel):
    """Represents a Dota 2 player.

    Attributes:
        name: Player name
        id: Unique player ID
        games: League games played for the team in the roster window (only set for rosters from recent matches)
        is_core: Played enough of the window games to be in the core, 75% (or 50%); players outside the core
            are stand-ins (only set for rosters from recent matches)
    """

    name: str
    id: int
    games: Optional[int] = None
    is_core: Optional[bool] = None


class FarmStats(BaseModel):
    """Medians of the team's highest and second highest GPM and XPM per league game.

    GPM and XPM are ranked separately: the top GPM and the top XPM of a game can belong to different players.

    Attributes:
        games: Number of games with known GPM and XPM
        gold_per_min_top1: Median of the highest gold per minute
        gold_per_min_top2: Median of the second highest gold per minute
        xp_per_min_top1: Median of the highest experience per minute
        xp_per_min_top2: Median of the second highest experience per minute
    """

    games: int
    gold_per_min_top1: float
    gold_per_min_top2: float
    xp_per_min_top1: float
    xp_per_min_top2: float


class LeagueForm(BaseModel):
    """League results of a team over a recent period.

    Attributes:
        days: Length of the period in days
        matches: Number of league matches in the period
        wins: Number of league wins
        losses: Number of league losses
        win_percentage: Wins share in percent (None when there are no matches)
        last_match_time: Start time of the latest league match (unix seconds)
        radiant_matches: League matches played on Radiant
        radiant_wins: League wins on Radiant
        radiant_win_percentage: Radiant wins share in percent (None when the team never played on Radiant)
        duration_median: Median match length in seconds (None when no duration is known)
        farm: Top 1 and top 2 GPM and XPM medians (None when no game has known GPM and XPM)
    """

    days: int
    matches: int = 0
    wins: int = 0
    losses: int = 0
    win_percentage: Optional[float] = None
    last_match_time: Optional[int] = None
    radiant_matches: int = 0
    radiant_wins: int = 0
    radiant_win_percentage: Optional[float] = None
    duration_median: Optional[float] = None
    farm: Optional[FarmStats] = None


class TeamRoster(BaseModel):
    """Active roster resolved from the team's recent league matches.

    Attributes:
        players: Main roster: the ROSTER_SIZE players with the most league games in the activity window
            (empty when there was no league match in the window or the API failed)
        other_players: Other active players: played league games for the team in the window but not enough
            for the main roster (a backup, a replaced player). Players without games in the window are not included.
        standins_count: Stand-ins: players who played in the window but are outside the core (`is_core` False);
            without a clear core, the players outside the main roster
        games_checked: Number of league games in the window whose lineup was looked at
        last_match_id: Latest league match played by at least ROSTER_MAJORITY main roster players
        last_match_time: Start time of that match (unix seconds)
        latest_match_time: Start time of the team's latest league match (unix seconds)
        latest_match_standins: Players of the latest league match who are not in the core
        roster_state: ROSTER_STABLE, ROSTER_STANDINS or ROSTER_NEW_TEAM;
            see classify_roster
        league_form: League results over the activity window
    """

    players: List[Player] = Field(default_factory=list)
    other_players: List[Player] = Field(default_factory=list)
    standins_count: int = 0
    games_checked: int = 0
    last_match_id: Optional[int] = None
    last_match_time: Optional[int] = None
    latest_match_time: Optional[int] = None
    latest_match_standins: Optional[int] = None
    roster_state: Optional[str] = None
    league_form: Optional[LeagueForm] = None


class TeamStats(BaseModel):
    """Statistics and information for a Dota 2 team.

    Attributes:
        team_id: Unique team identifier (None if error occurred)
        team: Team name
        tag: Team tag/abbreviation
        rating: Team's Elo ranking
        delta: Recent rating change
        rating_change: Estimated rating change over the `days` window (see backend.ratings)
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
    rating_change: Optional[float] = None
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

    def apply_roster(self, roster: TeamRoster, listed_players: List[Player]) -> None:
        """Take the players and roster details from a roster resolved from recent league matches.

        Args:
            roster: Roster with at least one player
            listed_players: Team members from pro_players who did not play in the window (kept last)
        """
        self.players = roster.players
        self.other_players = [*roster.other_players, *listed_players]
        self.roster_source = "recent_matches"
        self.roster_games = roster.games_checked
        self.standins_count = roster.standins_count
        self.roster_last_match_time = roster.last_match_time
        self.latest_match_time = roster.latest_match_time
        self.latest_match_standins = roster.latest_match_standins
        self.roster_state = roster.roster_state


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

    @classmethod
    def from_api(cls, row: dict[str, Any]) -> MatchStats:
        """Create from a /players/{id}/matches row.

        Raises:
            pydantic.ValidationError: If the row is malformed
        """
        return cls.model_validate(row)

    @property
    def won(self) -> bool:
        """Whether the player's side won the match."""
        return is_radiant(self.player_slot) == self.radiant_win


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

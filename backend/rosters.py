"""Resolve real team rosters and league form from recent league matches.

OpenDota's team membership data (`/proPlayers` team_id, `/teams/{id}/players`) is often stale,
so the roster is taken from the players who actually played the team's recent league matches.

Requests are kept low by caching in d2ba.sqlite:
- `/teams/{team_id}/matches` (one request returns the whole league history) is cached for TEAM_MATCHES_TTL.
- Match lineups never change once a match is finished, so they are cached forever. Missing lineups are
  fetched with one explorer `match_id IN (...)` query per batch of matches.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterable
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from backend.logging_config import setup_logging
from backend.opendota import OPENDOTA_API, OpenDotaError, get_json, is_radiant
from backend.pro_players import Player, get_d2ba_db

logger = setup_logging(__name__)

TEAM_MATCHES_TTL = 2 * 60 * 60  # 2 hours
TEAM_MATCHES_KEEP_DAYS = 365  # Older league matches are not stored
ROSTER_DAYS = 20  # Activity window; same default as the match history window (`days`) used for player stats
ROSTER_MAX_GAMES = 40  # At most this many of the newest league games inside the window are looked up
ROSTER_SIZE = 5  # Main roster size: the players with the most games in the window
ROSTER_MAJORITY = 3  # A game with at least this many main roster players counts as played by the roster
LINEUP_BATCH_SIZE = 20  # Match lineups fetched by one explorer query
CORE_GAME_SHARES = (0.75, 0.5)  # Core = players with at least this share of the window games; tried in order
ROSTER_STABLE = "stable"  # Only the core played
ROSTER_STANDINS = "standins"  # A clear core, plus stand-ins in some games
ROSTER_NEW_TEAM = "new_team"  # No clear core of ROSTER_SIZE players
DAY_SECONDS = 24 * 60 * 60
REQUEST_TIMEOUT = 30


def window_start(days: int, now: int) -> int:
    """Unix time `days` days before `now`: the start of an activity window."""
    return now - days * DAY_SECONDS


class TeamMatch(BaseModel):
    """One league match of a team, from the team's point of view.

    Attributes:
        match_id: Match identifier
        start_time: Match start time (unix seconds)
        leagueid: League identifier (0 or None for non-league matches)
        radiant: Whether the team played on Radiant
        radiant_win: Whether Radiant won
        opposing_team_id: Opponent team identifier
    """

    match_id: int
    start_time: int
    leagueid: Optional[int] = None
    radiant: bool
    radiant_win: Optional[bool] = None
    opposing_team_id: Optional[int] = None

    @classmethod
    def from_api(cls, row: dict[str, Any]) -> TeamMatch:
        """Create from a /teams/{id}/matches row.

        Raises:
            KeyError, TypeError, ValueError: If the row is malformed
        """
        return cls(
            match_id=int(row["match_id"]),
            start_time=int(row["start_time"]),
            leagueid=row.get("leagueid"),
            radiant=bool(row["radiant"]),
            radiant_win=row.get("radiant_win"),
            opposing_team_id=row.get("opposing_team_id"),
        )

    @classmethod
    def from_db(cls, row: sqlite3.Row) -> TeamMatch:
        """Create from a cached team_matches row."""
        return cls(
            match_id=row["match_id"],
            start_time=row["start_time"],
            leagueid=row["leagueid"],
            radiant=bool(row["radiant"]),
            radiant_win=None if row["radiant_win"] is None else bool(row["radiant_win"]),
            opposing_team_id=row["opposing_team_id"],
        )

    @property
    def won(self) -> Optional[bool]:
        """Whether the team won the match (None if the result is unknown)."""
        if self.radiant_win is None:
            return None
        return self.radiant == self.radiant_win


class LeagueForm(BaseModel):
    """League results of a team over a recent period.

    Attributes:
        days: Length of the period in days
        matches: Number of league matches in the period
        wins: Number of league wins
        losses: Number of league losses
        win_percentage: Wins share in percent (None when there are no matches)
        last_match_time: Start time of the latest league match (unix seconds)
    """

    days: int
    matches: int = 0
    wins: int = 0
    losses: int = 0
    win_percentage: Optional[float] = None
    last_match_time: Optional[int] = None


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


def _get_json(url: str, params: Optional[dict[str, Any]] = None) -> Any:
    """GET a URL and return parsed JSON, or None on any error.

    Args:
        url: URL to fetch
        params: Optional query parameters

    Returns:
        Parsed JSON payload or None
    """
    try:
        return get_json(url, params=params, timeout=REQUEST_TIMEOUT)
    except OpenDotaError as exc:
        logger.warning(f"Failed to fetch {url}: {exc}")
        return None


def _parse_team_match(row: dict[str, Any]) -> Optional[TeamMatch]:
    """Convert a /teams/{id}/matches row into a TeamMatch (None if malformed)."""
    try:
        return TeamMatch.from_api(row)
    except (KeyError, TypeError, ValueError):
        return None


def _load_cached_team_matches(team_id: int, now: int) -> Optional[list[TeamMatch]]:
    """Return cached team matches if they are fresh, otherwise None."""
    try:
        db = get_d2ba_db()
        sync = db.execute("SELECT fetched_at FROM team_matches_sync WHERE team_id = ?", (team_id,)).fetchone()
        if sync is None or now - int(sync["fetched_at"]) > TEAM_MATCHES_TTL:
            return None
        rows = db.execute(
            "SELECT match_id, start_time, leagueid, radiant, radiant_win, opposing_team_id "
            "FROM team_matches WHERE team_id = ? ORDER BY start_time DESC",
            (team_id,),
        ).fetchall()
        return [TeamMatch.from_db(row) for row in rows]
    except sqlite3.Error as exc:
        logger.warning(f"Team matches cache unavailable (run scripts/init_d2ba_db.py): {exc}")
        return None


def _store_team_matches(team_id: int, matches: Iterable[TeamMatch], now: int) -> None:
    """Replace cached matches of a team and mark them as fetched now."""
    try:
        db = get_d2ba_db()
        db.execute("DELETE FROM team_matches WHERE team_id = ?", (team_id,))
        db.executemany(
            "INSERT OR REPLACE INTO team_matches (team_id, match_id, start_time, leagueid, radiant, radiant_win, "
            "opposing_team_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    team_id,
                    m.match_id,
                    m.start_time,
                    m.leagueid,
                    m.radiant,
                    m.radiant_win,
                    m.opposing_team_id,
                )
                for m in matches
            ],
        )
        db.execute(
            "INSERT OR REPLACE INTO team_matches_sync (team_id, fetched_at) VALUES (?, ?)",
            (team_id, now),
        )
        db.commit()
    except sqlite3.Error as exc:
        logger.warning(f"Failed to cache team matches for team {team_id}: {exc}")


def get_team_league_matches(team_id: int, now: Optional[int] = None) -> list[TeamMatch]:
    """Get league matches of a team, newest first (cached for TEAM_MATCHES_TTL).

    Args:
        team_id: Team identifier
        now: Current unix time (for tests)

    Returns:
        List of TeamMatch objects sorted by start_time descending (empty on API failure)
    """
    now = now if now is not None else int(time.time())
    cached = _load_cached_team_matches(team_id, now)
    if cached is not None:
        return cached

    payload = _get_json(f"{OPENDOTA_API}/teams/{team_id}/matches")
    if not isinstance(payload, list):
        return []

    min_time = window_start(TEAM_MATCHES_KEEP_DAYS, now)
    matches = [m for m in (_parse_team_match(row) for row in payload if isinstance(row, dict)) if m]
    matches = [m for m in matches if m.start_time >= min_time and m.leagueid]
    matches.sort(key=lambda m: m.start_time, reverse=True)
    _store_team_matches(team_id, matches, now)
    return matches


def _load_cached_lineup(match_id: int) -> Optional[list[tuple[int, int]]]:
    """Return cached (player_slot, account_id) rows for a match, or None if not cached."""
    try:
        rows = (
            get_d2ba_db()
            .execute(
                "SELECT player_slot, account_id FROM match_players WHERE match_id = ? ORDER BY player_slot",
                (match_id,),
            )
            .fetchall()
        )
    except sqlite3.Error as exc:
        logger.warning(f"Lineup cache unavailable (run scripts/init_d2ba_db.py): {exc}")
        return None
    if not rows:
        return None
    return [(row["player_slot"], row["account_id"]) for row in rows]


def _store_lineup(match_id: int, lineup: list[tuple[int, int]]) -> None:
    """Cache a match lineup."""
    try:
        db = get_d2ba_db()
        db.executemany(
            "INSERT OR REPLACE INTO match_players (match_id, player_slot, account_id) VALUES (?, ?, ?)",
            [(match_id, slot, account_id) for slot, account_id in lineup],
        )
        db.commit()
    except sqlite3.Error as exc:
        logger.warning(f"Failed to cache lineup for match {match_id}: {exc}")


def _rows_to_lineup(rows: Any) -> list[tuple[int, int]]:
    """Extract (player_slot, account_id) pairs from explorer rows or /matches players."""
    lineup: list[tuple[int, int]] = []
    if not isinstance(rows, list):
        return lineup
    for row in rows:
        if not isinstance(row, dict):
            continue
        slot, account_id = row.get("player_slot"), row.get("account_id")
        if isinstance(slot, int) and isinstance(account_id, int):
            lineup.append((slot, account_id))
    return lineup


def _fetch_lineup_batch(match_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    """Fetch explorer rows of several matches with one `match_id IN (...)` query, grouped by match."""
    ids = ",".join(str(int(match_id)) for match_id in match_ids)
    sql = f"SELECT match_id, player_slot, account_id FROM player_matches WHERE match_id IN ({ids})"
    payload = _get_json(f"{OPENDOTA_API}/explorer", params={"sql": sql})
    rows = payload.get("rows") if isinstance(payload, dict) else None
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and isinstance(row.get("match_id"), int):
            grouped.setdefault(row["match_id"], []).append(row)
    return grouped


def get_match_lineups(match_ids: Iterable[int]) -> dict[int, list[tuple[int, int]]]:
    """Get (player_slot, account_id) of all players of several matches (cached forever).

    Matches missing from the cache are fetched with one explorer query per LINEUP_BATCH_SIZE matches.
    A match the explorer returns incomplete falls back to /matches/{id}, which is much larger.
    Both teams are cached, so the opponent's lineup of the same match costs nothing later.

    Args:
        match_ids: Match identifiers

    Returns:
        Lineup per match id (an empty or short list when unavailable)
    """
    lineups: dict[int, list[tuple[int, int]]] = {}
    missing: list[int] = []
    for match_id in dict.fromkeys(match_ids):
        cached = _load_cached_lineup(match_id)
        if cached is not None:
            lineups[match_id] = cached
        else:
            missing.append(match_id)

    for start in range(0, len(missing), LINEUP_BATCH_SIZE):
        batch = missing[start : start + LINEUP_BATCH_SIZE]
        grouped = _fetch_lineup_batch(batch)
        for match_id in batch:
            lineup = _rows_to_lineup(grouped.get(match_id))
            if len(lineup) < 10:
                payload = _get_json(f"{OPENDOTA_API}/matches/{int(match_id)}")
                fallback = _rows_to_lineup(payload.get("players") if isinstance(payload, dict) else None)
                if len(fallback) > len(lineup):
                    lineup = fallback
            if len(lineup) >= 10:
                _store_lineup(match_id, lineup)
            lineups[match_id] = lineup
    return lineups


def get_match_lineup(match_id: int) -> list[tuple[int, int]]:
    """Get (player_slot, account_id) of all players of one match (cached forever).

    Args:
        match_id: Match identifier

    Returns:
        List of (player_slot, account_id) tuples (empty if unavailable)
    """
    return get_match_lineups([match_id]).get(match_id, [])


def _team_side_accounts(lineup: list[tuple[int, int]], radiant: bool) -> list[int]:
    """Return account ids of the players on the given side, ordered by slot."""
    return [account_id for slot, account_id in sorted(lineup) if is_radiant(slot) == radiant and account_id]


def _player_names(account_ids: list[int]) -> dict[int, str]:
    """Look up player names from the local pro_players table."""
    if not account_ids:
        return {}
    try:
        placeholders = ",".join("?" for _ in account_ids)
        rows = (
            get_d2ba_db()
            .execute(
                f"SELECT account_id, name, personaname FROM pro_players WHERE account_id IN ({placeholders})",
                account_ids,
            )
            .fetchall()
        )
    except sqlite3.Error as exc:
        logger.warning(f"Failed to look up player names: {exc}")
        return {}
    return {row["account_id"]: (row["name"] or row["personaname"] or "").strip() for row in rows}


def _to_players(account_ids: list[int], names: dict[int, str], games: dict[int, int]) -> list[Player]:
    """Build Player objects with their league game count, using the account id when the name is unknown."""
    return [
        Player(id=account_id, name=names.get(account_id) or f"#{account_id}", games=games.get(account_id))
        for account_id in account_ids
    ]


def compute_league_form(matches: list[TeamMatch], days: int, now: Optional[int] = None) -> LeagueForm:
    """Summarize league results of a team over the last `days` days.

    Args:
        matches: Team league matches
        days: Period length in days
        now: Current unix time (for tests)

    Returns:
        LeagueForm with match, win and loss counts
    """
    now = now if now is not None else int(time.time())
    min_time = window_start(days, now)
    recent = [m for m in matches if m.start_time >= min_time and m.won is not None]
    wins = sum(1 for m in recent if m.won)
    return LeagueForm(
        days=days,
        matches=len(recent),
        wins=wins,
        losses=len(recent) - wins,
        win_percentage=100 * wins / len(recent) if recent else None,
        last_match_time=max((m.start_time for m in recent), default=None),
    )


def _team_lineups(
    matches: Iterable[TeamMatch], lineups: dict[int, list[tuple[int, int]]]
) -> list[tuple[TeamMatch, list[int]]]:
    """The team's side of each match, skipping matches with an incomplete lineup."""
    result = []
    for match in matches:
        accounts = _team_side_accounts(lineups.get(match.match_id, []), match.radiant)
        if len(accounts) >= 5:
            result.append((match, accounts))
    return result


def classify_roster(games: dict[int, int], total_games: int) -> tuple[set[int], str]:
    """Find the core players and the roster state from games played together in the window.

    - Core: players with at least CORE_GAME_SHARES[0] (75%) of the games. When that does not give exactly
      ROSTER_SIZE players, the next share (50%) is tried. When no share gives ROSTER_SIZE players, there is no
      clear core and the team counts as a new team. Everyone else who played is a stand-in.
    - State: only the core played = stable; a clear core plus stand-ins = stand-ins; no clear core = new team,
      the worst state for statistics.

    Args:
        games: Window games played per account
        total_games: Number of window games

    Returns:
        Tuple of (core accounts, empty when there is no clear core; roster state)
    """
    core: set[int] = set()
    for share in CORE_GAME_SHARES:
        candidates = {a for a, n in games.items() if n >= share * total_games}
        if len(candidates) == ROSTER_SIZE:
            core = candidates
            break

    if not core:
        state = ROSTER_NEW_TEAM
    elif len(games) == len(core):
        state = ROSTER_STABLE
    else:
        state = ROSTER_STANDINS
    return core, state


def resolve_roster(team_id: int, days: int = ROSTER_DAYS, now: Optional[int] = None) -> TeamRoster:
    """Resolve the team's main roster and other active players from its league matches.

    - Every league game of the last `days` days is looked up (the newest ROSTER_MAX_GAMES at most).
    - `players` are the ROSTER_SIZE players with the most of those games (ties: who played more recently),
      whether or not they played the latest game. Everyone else who played in the window goes to `other_players`.
    - Core players and the roster state come from classify_roster.

    Cost: 1 request for the team's matches (cached for TEAM_MATCHES_TTL) plus one explorer request per
    LINEUP_BATCH_SIZE games not cached yet; lineups are cached forever.

    Args:
        team_id: Team identifier
        days: Activity window in days
        now: Current unix time (for tests)

    Returns:
        TeamRoster; `players` is empty when there was no league match in the window or the API failed
    """
    now = now if now is not None else int(time.time())
    matches = get_team_league_matches(team_id, now=now)
    roster = TeamRoster(league_form=compute_league_form(matches, days, now=now))

    recent = [m for m in matches if m.start_time >= window_start(days, now)][:ROSTER_MAX_GAMES]
    lineups = get_match_lineups(m.match_id for m in recent) if recent else {}
    window = _team_lineups(recent, lineups)
    if not window:
        return roster

    games: dict[int, int] = {}
    last_played: dict[int, int] = {}
    for match, accounts in window:
        for account_id in accounts:
            games[account_id] = games.get(account_id, 0) + 1
            last_played[account_id] = max(last_played.get(account_id, 0), match.start_time)
    ranked = sorted(games, key=lambda a: (-games[a], -last_played[a]))
    active, others = ranked[:ROSTER_SIZE], ranked[ROSTER_SIZE:]
    active_set = set(active)

    core, state = classify_roster(games, len(window))
    # Without a clear core, everyone outside the main roster counts as a stand-in
    core_set = core or active_set

    names = _player_names([*active, *others])
    roster.players = _to_players(active, names, games)
    roster.other_players = _to_players(others, names, games)
    for player in [*roster.players, *roster.other_players]:
        player.is_core = player.id in core
    roster.standins_count = sum(1 for a in ranked if a not in core_set)
    roster.roster_state = state
    roster.games_checked = len(window)

    # The roster's own latest game: the newest one that most of the roster played together
    main, _ = next(
        ((m, acc) for m, acc in window if len(active_set.intersection(acc)) >= ROSTER_MAJORITY),
        window[0],
    )
    roster.last_match_id = main.match_id
    roster.last_match_time = main.start_time

    latest, latest_accounts = window[0]
    roster.latest_match_time = latest.start_time
    roster.latest_match_standins = sum(1 for a in latest_accounts if a not in core_set)
    return roster

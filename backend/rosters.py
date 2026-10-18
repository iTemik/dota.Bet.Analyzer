"""Resolve real team rosters and league form from recent league matches.

OpenDota's team membership data (`/proPlayers` team_id, `/teams/{id}/players`) is often stale,
so the roster is taken from the players who actually played the team's latest league matches.

Requests are kept low by caching in d2ba.sqlite:
- `/teams/{team_id}/matches` (one request returns the whole league history) is cached for TEAM_MATCHES_TTL.
- Match lineups never change once a match is finished, so they are cached forever.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterable
from typing import Any, List, Optional

import requests
from pydantic import BaseModel, Field

from backend.logging_config import setup_logging
from backend.pro_players import Player, get_d2ba_db

logger = setup_logging(__name__)

OPENDOTA_API = "https://api.opendota.com/api"
TEAM_MATCHES_TTL = 2 * 60 * 60  # 2 hours
TEAM_MATCHES_KEEP_DAYS = 365  # Older league matches are not stored
ROSTER_DAYS = 60
ROSTER_SERIES = 3
SERIES_GAP_SECONDS = 8 * 60 * 60  # Games against the same opponent closer than this belong to one series
RADIANT_SLOT_LIMIT = 128  # player_slot < 128 is Radiant
REQUEST_TIMEOUT = 30


class TeamMatch(BaseModel):
    """One league match of a team, from the team's point of view.

    Attributes:
        match_id: Match identifier
        start_time: Match start time (unix seconds)
        leagueid: League identifier (0 or None for non-league matches)
        league_name: League name
        radiant: Whether the team played on Radiant
        radiant_win: Whether Radiant won
        opposing_team_id: Opponent team identifier
        opposing_team_name: Opponent team name
    """

    match_id: int
    start_time: int
    leagueid: Optional[int] = None
    league_name: Optional[str] = None
    radiant: bool
    radiant_win: Optional[bool] = None
    opposing_team_id: Optional[int] = None
    opposing_team_name: Optional[str] = None

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
    """Roster resolved from the team's recent league matches.

    Attributes:
        players: Lineup of the latest league match (empty when no recent league match was found)
        standins: Players of the latest lineup who did not play the older checked series
        series_checked: Number of distinct series whose lineup was looked at
        last_match_id: Latest league match the lineup was taken from
        last_match_time: Start time of that match (unix seconds)
        league_form: League results over the roster period
    """

    players: List[Player] = Field(default_factory=list)
    standins: List[Player] = Field(default_factory=list)
    series_checked: int = 0
    last_match_id: Optional[int] = None
    last_match_time: Optional[int] = None
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
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            logger.warning(f"HTTP {resp.status_code} from {url}")
            return None
        return resp.json()
    except Exception as exc:
        logger.warning(f"Failed to fetch {url}: {exc}")
        return None


def _parse_team_match(row: dict[str, Any]) -> Optional[TeamMatch]:
    """Convert a /teams/{id}/matches row into a TeamMatch (None if malformed)."""
    try:
        return TeamMatch(
            match_id=int(row["match_id"]),
            start_time=int(row["start_time"]),
            leagueid=row.get("leagueid"),
            league_name=(row.get("league_name") or "").strip() or None,
            radiant=bool(row["radiant"]),
            radiant_win=row.get("radiant_win"),
            opposing_team_id=row.get("opposing_team_id"),
            opposing_team_name=row.get("opposing_team_name"),
        )
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
            "SELECT match_id, start_time, leagueid, league_name, radiant, radiant_win, opposing_team_id, "
            "opposing_team_name FROM team_matches WHERE team_id = ? ORDER BY start_time DESC",
            (team_id,),
        ).fetchall()
        return [
            TeamMatch(
                match_id=row["match_id"],
                start_time=row["start_time"],
                leagueid=row["leagueid"],
                league_name=row["league_name"],
                radiant=bool(row["radiant"]),
                radiant_win=None if row["radiant_win"] is None else bool(row["radiant_win"]),
                opposing_team_id=row["opposing_team_id"],
                opposing_team_name=row["opposing_team_name"],
            )
            for row in rows
        ]
    except sqlite3.Error as exc:
        logger.warning(f"Team matches cache unavailable (run scripts/init_d2ba_db.py): {exc}")
        return None


def _store_team_matches(team_id: int, matches: Iterable[TeamMatch], now: int) -> None:
    """Replace cached matches of a team and mark them as fetched now."""
    try:
        db = get_d2ba_db()
        db.execute("DELETE FROM team_matches WHERE team_id = ?", (team_id,))
        db.executemany(
            "INSERT OR REPLACE INTO team_matches (team_id, match_id, start_time, leagueid, league_name, radiant, "
            "radiant_win, opposing_team_id, opposing_team_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    team_id,
                    m.match_id,
                    m.start_time,
                    m.leagueid,
                    m.league_name,
                    m.radiant,
                    m.radiant_win,
                    m.opposing_team_id,
                    m.opposing_team_name,
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

    min_time = now - TEAM_MATCHES_KEEP_DAYS * 24 * 60 * 60
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


def get_match_lineup(match_id: int) -> list[tuple[int, int]]:
    """Get (player_slot, account_id) of all players of a match (cached forever).

    Uses a small single-match explorer query first; falls back to /matches/{id} which is much larger.
    Both teams are cached, so the opponent's lineup of the same match costs nothing later.

    Args:
        match_id: Match identifier

    Returns:
        List of (player_slot, account_id) tuples (empty if unavailable)
    """
    cached = _load_cached_lineup(match_id)
    if cached is not None:
        return cached

    sql = f"SELECT player_slot, account_id FROM player_matches WHERE match_id = {int(match_id)}"
    payload = _get_json(f"{OPENDOTA_API}/explorer", params={"sql": sql})
    lineup = _rows_to_lineup(payload.get("rows") if isinstance(payload, dict) else None)

    if len(lineup) < 10:
        payload = _get_json(f"{OPENDOTA_API}/matches/{int(match_id)}")
        fallback = _rows_to_lineup(payload.get("players") if isinstance(payload, dict) else None)
        if len(fallback) > len(lineup):
            lineup = fallback

    if len(lineup) >= 10:
        _store_lineup(match_id, lineup)
    return lineup


def _team_side_accounts(lineup: list[tuple[int, int]], radiant: bool) -> list[int]:
    """Return account ids of the players on the given side, ordered by slot."""
    return [account_id for slot, account_id in sorted(lineup) if (slot < RADIANT_SLOT_LIMIT) == radiant and account_id]


def _latest_match_per_series(matches: list[TeamMatch], limit: int) -> list[TeamMatch]:
    """Pick the newest match of each of the latest `limit` series.

    Consecutive matches against the same opponent in the same league with less than
    SERIES_GAP_SECONDS between them are treated as one series.

    Args:
        matches: Team matches sorted newest first
        limit: Maximum number of series

    Returns:
        Newest match of each series, newest series first
    """
    picked: list[TeamMatch] = []
    previous: Optional[TeamMatch] = None
    for match in matches:
        same_series = (
            previous is not None
            and match.opposing_team_id == previous.opposing_team_id
            and match.leagueid == previous.leagueid
            and previous.start_time - match.start_time < SERIES_GAP_SECONDS
        )
        if not same_series:
            if len(picked) >= limit:
                break
            picked.append(match)
        previous = match
    return picked


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


def _to_players(account_ids: list[int], names: dict[int, str]) -> list[Player]:
    """Build Player objects, using the account id when the name is unknown."""
    return [Player(id=account_id, name=names.get(account_id) or f"#{account_id}") for account_id in account_ids]


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
    min_time = now - days * 24 * 60 * 60
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


def resolve_roster(
    team_id: int,
    days: int = ROSTER_DAYS,
    series: int = ROSTER_SERIES,
    now: Optional[int] = None,
) -> TeamRoster:
    """Resolve the team's current lineup from its latest league matches.

    The roster is the lineup of the latest league match within `days`. The latest match of up to
    `series` recent series is checked; players of the latest lineup who did not appear in any of the
    older checked series are reported as possible stand-ins.

    Cost: 1 request for the team's matches (cached for TEAM_MATCHES_TTL) plus at most `series`
    lineup requests (cached forever).

    Args:
        team_id: Team identifier
        days: Only matches newer than this many days are used
        series: Number of recent series to check
        now: Current unix time (for tests)

    Returns:
        TeamRoster; `players` is empty when there was no league match in the period or the API failed
    """
    now = now if now is not None else int(time.time())
    matches = get_team_league_matches(team_id, now=now)
    roster = TeamRoster(league_form=compute_league_form(matches, days, now=now))

    min_time = now - days * 24 * 60 * 60
    recent = [m for m in matches if m.start_time >= min_time]

    lineups: list[list[int]] = []
    latest: Optional[TeamMatch] = None
    for match in _latest_match_per_series(recent, series):
        accounts = _team_side_accounts(get_match_lineup(match.match_id), match.radiant)
        if len(accounts) < 5:
            continue
        if latest is None:
            latest = match
        lineups.append(accounts)

    if latest is None:
        return roster

    newest, older = lineups[0], lineups[1:]
    older_accounts = {account_id for lineup in older for account_id in lineup}
    standin_ids = [account_id for account_id in newest if older and account_id not in older_accounts]

    names = _player_names(newest)
    roster.players = _to_players(newest, names)
    roster.standins = _to_players(standin_ids, names)
    roster.series_checked = len(lineups)
    roster.last_match_id = latest.match_id
    roster.last_match_time = latest.start_time
    return roster

"""Pro Players database operations."""

import os
import sqlite3
import time
from collections.abc import Iterable, Mapping
from typing import Any, Optional, cast

import requests
from flask import current_app, g
from pydantic import BaseModel

from backend.logging_config import setup_logging

logger = setup_logging(__name__)


class Player(BaseModel):
    """Represents a Dota 2 player.

    Attributes:
        name: Player name
        id: Unique player ID
    """

    name: str
    id: int


def get_d2ba_db():
    """Get connection to d2ba.sqlite database."""
    if "d2ba_db" not in g:
        db_path = os.path.join(current_app.instance_path, "d2ba.sqlite")
        g.d2ba_db = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        g.d2ba_db.row_factory = sqlite3.Row
    return g.d2ba_db


def close_d2ba_db(e=None):
    """Close d2ba database connection."""
    db = g.pop("d2ba_db", None)
    if db is not None:
        db.close()


def fetch_pro_players_from_api() -> list[dict[str, Any]]:
    """Fetch pro players data from OpenDota API.

    Returns:
        List of pro player dictionaries.

    Raises:
        ConnectionError: If unable to connect to or get response from OpenDota API.
        ValueError: If API response is invalid or not a list.
    """
    try:
        response = requests.get("https://api.opendota.com/api/proPlayers", timeout=30)
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, list):
            raise ValueError(f"Expected list from API, got {type(data).__name__}")

        return data

    except requests.RequestException as e:
        raise ConnectionError(f"Failed to fetch pro players from OpenDota API: {e}") from e
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Unexpected error parsing pro players response: {e}") from e


def store_pro_players(players_data: list[dict[str, Any]]) -> int:
    """Store pro players data to database.

    Args:
        players_data: List of player dictionaries from OpenDota API

    Returns:
        Number of players stored/updated
    """
    if not players_data:
        return 0

    start_time = time.time()
    db = get_d2ba_db()
    cursor = db.cursor()

    count = 0
    for player in players_data:
        # Extract only the fields we need
        try:
            cursor.execute(
                """
                INSERT INTO pro_players (
                    account_id, steamid, profileurl, personaname, name,
                    fantasy_role, team_id, team_name, team_tag, is_pro
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                    steamid = excluded.steamid,
                    profileurl = excluded.profileurl,
                    personaname = excluded.personaname,
                    name = excluded.name,
                    fantasy_role = excluded.fantasy_role,
                    team_id = excluded.team_id,
                    team_name = excluded.team_name,
                    team_tag = excluded.team_tag,
                    is_pro = excluded.is_pro
                """,
                (
                    player.get("account_id"),
                    player.get("steamid"),
                    player.get("profileurl"),
                    player.get("personaname"),
                    player.get("name"),
                    player.get("fantasy_role"),
                    player.get("team_id"),
                    player.get("team_name"),
                    player.get("team_tag"),
                    player.get("is_pro"),
                ),
            )
            count += 1
        except sqlite3.Error:
            continue

    db.commit()
    elapsed = time.time() - start_time
    rate = count / elapsed if elapsed > 0 else 0.0
    logger.info(f"Stored/updated {count} pro players in {elapsed:.3f}s ({rate:.1f} records/sec)")
    return count


def init_d2ba_app(app):
    """Initialize d2ba database helpers for the app."""
    app.teardown_appcontext(close_d2ba_db)


def sync_pro_players_on_startup(app):
    """Fetch and store pro players data on app startup.

    This runs asynchronously to not block app initialization.
    Errors are logged but don't fail the app startup.
    """

    try:
        with app.app_context():
            logger.info("Fetching pro players from OpenDota API...")
            players_data = fetch_pro_players_from_api()

            if players_data is None:
                logger.warning("Failed to fetch pro players from OpenDota API")
                return

            if not players_data:
                logger.info("No pro players data available from OpenDota API")
                return

            count = store_pro_players(players_data)
            logger.info(f"Successfully stored {count} pro players to d2ba database")

    except Exception as e:
        logger.error(f"Error syncing pro players on startup: {e}")


def _extract_players_from_rows(rows: Iterable[Mapping[str, Any]]) -> tuple[list[Player], list[Player]]:
    """Extract Player objects from database rows.

    Processes an iterable of dict-like objects and separates them into pro and other players.
    Works with sqlite3.Row objects, dictionaries, or any Mapping

    Args:
        rows: Iterable of Mapping objects (e.g., sqlite3.Row, dict) with keys: account_id, name, is_pro

    Returns:
        Tuple of (pro_players, other_players) where:
        - pro_players: List of Player objects where is_pro=1
        - other_players: List of Player objects where is_pro is missing or !=0
    """
    # Import here to avoid circular imports
    from backend.stats import Player

    pro_players: list[Player] = []
    other_players: list[Player] = []
    total_rows = 0

    for row in rows:
        total_rows += 1
        if row["name"]:
            player = Player(name=row["name"], id=row["account_id"])
            if row["is_pro"] == 1:
                pro_players.append(player)
            else:
                other_players.append(player)

    logger.debug(
        f"Extracted {len(pro_players)} pro players and {len(other_players)} " f"other players from {total_rows} rows"
    )
    return pro_players, other_players


def get_players_by_team(
    team_id: Optional[int] = None, team_name: Optional[str] = None, team_tag: Optional[str] = None
) -> tuple[list[Player], list[Player]]:
    """Get Player objects from a team by team_id, team_name, or team_tag.

    Args:
        team_id: Team ID to search for
        team_name: Team name to search for (case-insensitive)
        team_tag: Team tag to search for (case-insensitive)

    Returns:
        Tuple of (pro_players, other_players) where:
        - pro_players: List of Player objects where is_pro=1
        - other_players: List of Player objects where is_pro is missing or !=0

    Raises:
        ValueError: If no search criteria provided
    """
    if not any([team_id, team_name, team_tag]):
        raise ValueError("At least one search criterion (team_id, team_name, or team_tag) must be provided")

    try:
        db = get_d2ba_db()
        cursor = db.cursor()

        # Build query dynamically based on provided criteria
        conditions: list[str] = []
        params: list[int | str] = []

        if team_id is not None:
            conditions.append("team_id = ?")
            params.append(team_id)

        if team_name is not None:
            conditions.append("LOWER(team_name) = LOWER(?)")
            params.append(team_name)

        if team_tag is not None:
            conditions.append("LOWER(team_tag) = LOWER(?)")
            params.append(team_tag)

        where_clause = " OR ".join(conditions) if conditions else "1=0"
        query = f"SELECT account_id, name, is_pro FROM pro_players WHERE {where_clause} ORDER BY name"

        logger.debug(f"Executing query: {query} with params: {params}")
        cursor.execute(query, params)
        db_rows = cast(Iterable[Mapping[str, Any]], cursor.fetchall())
        return _extract_players_from_rows(db_rows)

    except sqlite3.Error as e:
        # Log error but return empty lists
        logger.error(f"Error querying players by team: {e}")
        return [], []


def fetch_teams_from_api() -> list[dict[str, Any]]:
    """Fetch teams data from OpenDota API paginated by 1000 entries per page.

    The API returns up to 1000 teams per page. This function fetches all pages
    until it gets fewer than 1000 teams (indicating the last page) or reaches
    the maximum page limit (100 pages = 100,000+ teams).

    Returns:
        List of team dictionaries (may be partial if an error occurs after fetching
        some pages, but will raise exception if first page fails).

    Raises:
        ConnectionError: If unable to fetch the first page of teams.
        ValueError: If API response is invalid (not a list).

    Note:
        If a page fails after successfully fetching previous pages, returns the data
        collected so far rather than failing entirely (graceful degradation).
    """
    MAX_PAGES = 100
    all_teams = []
    page = 0

    try:
        while page < MAX_PAGES:
            try:
                response = requests.get(f"https://api.opendota.com/api/teams?page={page}", timeout=30)
                response.raise_for_status()
                data = response.json()

                if not isinstance(data, list):
                    error_msg = f"Page {page}: Expected list from API, got {type(data).__name__}"
                    logger.warning(error_msg)
                    if page == 0:
                        raise ValueError(error_msg)
                    break

                all_teams.extend(data)
                logger.debug(f"Fetched {len(data)} teams from page {page}")

                # If we got fewer than 1000 teams, it's the last page
                if len(data) < 1000:
                    logger.info(f"Fetched teams from {page + 1} pages (total: {len(all_teams)} teams)")
                    break

                page += 1

            except requests.RequestException as page_error:
                # If we have data from previous pages, return it (graceful degradation)
                if all_teams:
                    logger.warning(
                        f"Error fetching page {page}: {page_error}. "
                        f"Returning {len(all_teams)} teams fetched before error"
                    )
                    break

                # If this is the first page and it failed, raise exception (critical error)
                logger.error(f"Failed to fetch first page of teams: {page_error}")
                raise ConnectionError(f"Failed to fetch teams from OpenDota API: {page_error}") from page_error

        # Only raise ConnectionError if we never successfully fetched any page (page == 0)
        # If page > 0, we made successful API calls even if result is empty
        if not all_teams and page == 0:
            raise ConnectionError("No teams fetched from OpenDota API (empty response on first page)")

        return all_teams

    except (ConnectionError, ValueError):
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching teams from API: {e}")
        raise ConnectionError(f"Unexpected error fetching teams from API: {e}") from e


def store_teams(teams_data: list[dict[str, Any]]) -> int:
    """Store teams data to database.

    Args:
        teams_data: List of team dictionaries from OpenDota API

    Returns:
        Number of teams stored/updated
    """
    if not teams_data:
        return 0

    start_time = time.time()
    db = get_d2ba_db()
    cursor = db.cursor()

    count = 0
    for team in teams_data:
        try:
            cursor.execute(
                """
                INSERT INTO teams (
                    team_id, rating, name, tag, logo_url, last_match_time
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(team_id) DO UPDATE SET
                    rating = excluded.rating,
                    name = excluded.name,
                    tag = excluded.tag,
                    logo_url = excluded.logo_url,
                    last_match_time = excluded.last_match_time
                """,
                (
                    team.get("team_id"),
                    team.get("rating"),
                    team.get("name"),
                    team.get("tag"),
                    team.get("logo_url"),
                    team.get("last_match_time"),
                ),
            )
            count += 1
        except sqlite3.Error as e:
            logger.error(f"Error storing team {team.get('team_id')}: {e}")

    db.commit()
    elapsed = time.time() - start_time
    records_per_sec = (count / elapsed) if elapsed > 0 else 0.0
    logger.info(f"Stored/updated {count} teams in {elapsed:.3f}s ({records_per_sec:.1f} records/sec)")
    return count

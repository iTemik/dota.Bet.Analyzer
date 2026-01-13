"""Pro Players database operations."""

import os
import sqlite3
from typing import Any, Optional

import requests
from flask import current_app, g
from pydantic import BaseModel


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


def fetch_pro_players_from_api() -> Optional[list[dict[str, Any]]]:
    """Fetch pro players data from OpenDota API.

    Returns:
        List of pro player dictionaries, or None if request fails.
    """
    try:
        response = requests.get("https://api.opendota.com/api/proPlayers", timeout=30)
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, list):
            return None

        return data

    except Exception:
        return None


def store_pro_players(players_data: list[dict[str, Any]]) -> int:
    """Store pro players data to database.

    Args:
        players_data: List of player dictionaries from OpenDota API

    Returns:
        Number of players stored/updated
    """
    if not players_data:
        return 0

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
    return count


def init_d2ba_app(app):
    """Initialize d2ba database helpers for the app."""
    app.teardown_appcontext(close_d2ba_db)


def sync_pro_players_on_startup(app):
    """Fetch and store pro players data on app startup.

    This runs asynchronously to not block app initialization.
    Errors are logged but don't fail the app startup.
    """
    import logging

    logger = logging.getLogger(__name__)

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


def get_players_by_team(team_id: Optional[int] = None, team_name: Optional[str] = None, team_tag: Optional[str] = None):
    """Get Player objects from a team by team_id, team_name, or team_tag.

    Args:
        team_id: Team ID to search for
        team_name: Team name to search for (case-insensitive)
        team_tag: Team tag to search for (case-insensitive)

    Returns:
        List of Player objects matching the team criteria, or empty list if no matches

    Raises:
        ValueError: If no search criteria provided
    """
    import logging

    # Import here to avoid circular imports
    from backend.stats import Player

    logger = logging.getLogger(__name__)

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
        query = f"SELECT account_id, name FROM pro_players WHERE {where_clause} ORDER BY name"

        logger.debug(f"Executing query: {query} with params: {params}")
        cursor.execute(query, params)
        rows = cursor.fetchall()
        logger.debug(f"Query returned {len(rows)} rows")

        # Convert rows to Player objects
        players = []
        for row in rows:
            if row["name"]:
                players.append(Player(name=row["name"], id=row["account_id"]))
        logger.debug(f"Returning {len(players)} Player objects")
        return players

    except sqlite3.Error as e:
        # Log error but return empty list
        logger.error(f"Error querying players by team: {e}")
        return []

"""Hero list from OpenDota, cached in d2ba.sqlite.

One request to /constants/heroes fills the table. It is synced at startup only when the table is empty, and by
POST /api/heroes/sync. New heroes are rare, so there is no TTL.
"""

import sqlite3
from typing import Any

from backend.logging_config import setup_logging
from backend.opendota import OpenDotaError, get_json
from backend.pro_players import get_d2ba_db

logger = setup_logging(__name__)

HERO_IMAGE_HOST = "https://cdn.cloudflare.steamstatic.com"  # OpenDota icon paths are relative to the Steam CDN


def fetch_heroes_from_api() -> list[dict[str, Any]]:
    """Fetch the hero list from OpenDota /constants/heroes.

    Returns:
        Heroes with hero_id, name, localized_name and full icon URL; malformed entries are skipped

    Raises:
        ConnectionError: If OpenDota could not be reached or answered with an error
        ValueError: If the answer is not a JSON object keyed by hero id
    """
    try:
        data = get_json("/constants/heroes", timeout=30)
    except OpenDotaError as e:
        if e.code == "JSON_DECODE_ERROR":
            raise ValueError(f"Unexpected error parsing heroes response: {e}") from e
        raise ConnectionError(f"Failed to fetch heroes from OpenDota API: {e}") from e

    if not isinstance(data, dict):
        raise ValueError(f"Expected object from API, got {type(data).__name__}")

    heroes = []
    for entry in data.values():
        try:
            icon = entry.get("icon") or ""
            heroes.append(
                {
                    "hero_id": int(entry["id"]),
                    "name": str(entry["name"]),
                    "localized_name": str(entry["localized_name"]),
                    "icon": f"{HERO_IMAGE_HOST}{icon.rstrip('?')}" if icon.startswith("/") else icon,
                }
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            logger.warning(f"Skipping malformed hero entry: {entry!r}")
    return heroes


def store_heroes(heroes: list[dict[str, Any]]) -> int:
    """Insert or update heroes in d2ba.sqlite.

    Args:
        heroes: Heroes as returned by fetch_heroes_from_api

    Returns:
        Number of heroes stored
    """
    db = get_d2ba_db()
    db.executemany(
        """
        INSERT INTO heroes (hero_id, name, localized_name, icon) VALUES (:hero_id, :name, :localized_name, :icon)
        ON CONFLICT(hero_id) DO UPDATE SET
            name = excluded.name, localized_name = excluded.localized_name, icon = excluded.icon
        """,
        heroes,
    )
    db.commit()
    return len(heroes)


def list_heroes() -> list[dict[str, Any]]:
    """All cached heroes ordered by display name.

    Returns:
        Heroes with hero_id, name, localized_name and icon
    """
    rows = get_d2ba_db().execute("SELECT hero_id, name, localized_name, icon FROM heroes ORDER BY localized_name")
    return [dict(row) for row in rows]


def sync_heroes_if_empty() -> int:
    """Fill the heroes table from OpenDota when it is empty; no request when it already has heroes.

    Returns:
        Number of heroes stored (0 when the table was already filled)

    Raises:
        ConnectionError: If OpenDota could not be reached
        ValueError: If the OpenDota answer is invalid
    """
    if get_d2ba_db().execute("SELECT 1 FROM heroes LIMIT 1").fetchone() is not None:
        return 0
    return store_heroes(fetch_heroes_from_api())


def sync_heroes_on_startup(app) -> None:
    """Fill the heroes table at startup when it is empty. Errors are logged and don't fail the startup.

    Args:
        app: Flask app
    """
    try:
        with app.app_context():
            count = sync_heroes_if_empty()
            if count:
                logger.info(f"Stored {count} heroes to d2ba database")
    except (ConnectionError, ValueError, sqlite3.Error) as e:
        logger.error(f"Error syncing heroes on startup: {e}")

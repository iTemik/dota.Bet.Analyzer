"""Hero list from OpenDota, cached in d2ba.sqlite.

One request to /constants/heroes fills the table. The `heroes` cache job (backend.jobs) refreshes it weekly, and
POST /api/jobs/heroes/run on demand.
"""

from typing import Any

from backend.db import get_cache_db
from backend.logging_config import setup_logging
from backend.opendota import OpenDotaError, get_json

logger = setup_logging(__name__)

HERO_IMAGE_HOST = "https://cdn.cloudflare.steamstatic.com"  # OpenDota icon paths are relative to the Steam CDN


def fetch_heroes_from_api(background: bool = False) -> list[dict[str, Any]]:
    """Fetch the hero list from OpenDota /constants/heroes.

    Args:
        background: True for the cache job (goes after user requests, stops at the daily OpenDota budget)

    Returns:
        Heroes with hero_id, name, localized_name and full icon URL; malformed entries are skipped

    Raises:
        ConnectionError: If OpenDota could not be reached or answered with an error
        ValueError: If the answer is not a JSON object keyed by hero id
    """
    try:
        data = get_json("/constants/heroes", timeout=30, background=background)
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
    db = get_cache_db()
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
    rows = get_cache_db().execute("SELECT hero_id, name, localized_name, icon FROM heroes ORDER BY localized_name")
    return [dict(row) for row in rows]

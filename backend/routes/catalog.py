"""Catalog routes: backend version, heroes, hero meta, Liquipedia matches and team search."""

import os
import time

from flask import Response, current_app, jsonify

from backend import __version__
from backend.helpers import Errors, api_error
from backend.heroes import list_heroes
from backend.jobs import queue_job_if_due
from backend.logging_config import setup_logging
from backend.matches import get_matches
from backend.meta import MetaParams, get_meta
from backend.routes import ApiBlueprint
from backend.schemas import (
    HeroSchema,
    MatchesSchema,
    MetaQuerySchema,
    MetaSchema,
    TeamSchema,
    TeamSearchQuerySchema,
    VersionSchema,
)
from backend.team_meta import latest_patch

logger = setup_logging(__name__)


bp = ApiBlueprint("Catalog", __name__, description="Version, heroes, hero meta, matches and team search")


@bp.route("/version", methods=["GET"])
@bp.response(200, VersionSchema)
def get_version() -> tuple[Response, int]:
    """Get backend version.

    Returns backend version including build number.

    This endpoint always succeeds and returns 200 OK.
    """
    return (
        jsonify(
            {
                "backend": full_version(),
                "build": _build_number(),
            }
        ),
        200,
    )


def _build_number() -> str:
    """Build number of the running backend (DEV when not set)."""
    return os.environ.get("BUILD_NUMBER", "DEV")


def full_version() -> str:
    """Backend version with build number, as shown by /api/version."""
    return f"{__version__}.{_build_number()}"


def _sync_teams_if_obsolete() -> None:
    """Update the teams list in the background when it is obsolete (not in tests, which never reach OpenDota)."""
    if not current_app.config.get("TESTING"):
        queue_job_if_due("teams")


@bp.route("/heroes", methods=["GET"])
@bp.response(200, HeroSchema(many=True))
@bp.error_response(500, Errors.FAILED_TO_READ_HEROES, "Database operation failed")
def get_heroes() -> tuple[Response, int]:
    """List the cached heroes (id, names, icon URL) ordered by display name.

    Reads d2ba.sqlite only, no OpenDota request. The `heroes` cache job refreshes the list weekly, POST
    /jobs/heroes/run on demand.
    """
    try:
        return jsonify(list_heroes()), 200
    except Exception as e:
        return api_error(500, Errors.FAILED_TO_READ_HEROES, e)


@bp.route("/heroes/meta", methods=["GET"])
@bp.arguments(MetaQuerySchema, location="query")
@bp.response(200, MetaSchema)
@bp.error_response(503, Errors.FAILED_TO_FETCH_HERO_STATS, "OpenDota could not be reached or its answer was invalid")
def get_hero_meta(args: dict) -> tuple[Response, int]:
    """Pro meta, ultra meta and pub meta heroes from OpenDota /heroStats (about the last 7 days), and the latest patch.

    At most one OpenDota request per hour (cached in Redis), or per minute with `refresh=true`; the thresholds
    are query parameters, so changing them needs no new request.
    """
    try:
        refresh = args.pop("refresh", False)
        meta = get_meta(MetaParams(**args), refresh)
        patch = latest_patch(int(time.time()))  # Cached for a week, None when unknown
        return jsonify({**meta, "patch": patch["name"] if patch else None}), 200
    except ConnectionError as e:
        return api_error(503, Errors.FAILED_TO_FETCH_HERO_STATS, e)


@bp.route("/matches", methods=["GET"])
@bp.response(200, MatchesSchema)
@bp.error_response(503, Errors.FAILED_TO_FETCH_MATCHES, "Liquipedia could not be reached or its page could not be read")
@bp.error_response(500, Errors.UNEXPECTED_ERROR, "Database error")
def list_matches() -> tuple[Response, int]:
    """Upcoming (soonest first) and recently finished (newest first) pro series from Liquipedia.

    One Liquipedia request at most every 10 minutes (cached in Redis). Teams are matched by
    name to the teams table for their OpenDota ID and logo; an obsolete teams list is updated in the background.
    """
    _sync_teams_if_obsolete()
    try:
        return jsonify(get_matches()), 200
    except ConnectionError as e:
        return api_error(503, Errors.FAILED_TO_FETCH_MATCHES, e)
    except Exception as e:
        logger.error(f"Error listing matches: {e}")
        return api_error(500, Errors.UNEXPECTED_ERROR, e)


@bp.route("/teams/search", methods=["GET"])
@bp.arguments(TeamSearchQuerySchema, location="query")
@bp.response(200, TeamSchema(many=True))
@bp.error_response(422, Errors.VALIDATION_ERROR, "Invalid query parameters")
@bp.error_response(503, Errors.SEARCH_ERROR, "Database connection error")
def search_teams(args):
    """Search for teams by name or tag for autocomplete.

    Returns a list of matching teams ordered by relevance (starts-with matches first).
    """
    from backend.db import get_cache_db

    _sync_teams_if_obsolete()
    search_query = args["q"]
    limit = args.get("limit", 10)

    try:
        db = get_cache_db()
        cursor = db.cursor()

        # Search teams by name or tag (case-insensitive)
        # WHERE uses "contains" pattern; ORDER BY:
        #   1. Relevance tier: name starts-with (0) > tag starts-with (1) > contains (2)
        #   2. Within each tier: most recent last_match_time first
        #   3. Alphabetical as final tiebreaker
        cursor.execute(
            """
            SELECT team_id, name, tag, logo_url, rating, last_match_time
            FROM teams
            WHERE
              LOWER(name) LIKE LOWER(?) OR
              LOWER(tag) LIKE LOWER(?)
            ORDER BY
              CASE
                WHEN LOWER(name) LIKE LOWER(?) THEN 0
                WHEN LOWER(tag) LIKE LOWER(?) THEN 1
                ELSE 2
              END,
              COALESCE(last_match_time, 0) DESC,
              name
            LIMIT ?
            """,
            (
                f"%{search_query}%",  # name contains (WHERE)
                f"%{search_query}%",  # tag contains (WHERE)
                f"{search_query}%",  # name starts with (ORDER BY - highest priority)
                f"{search_query}%",  # tag starts with (ORDER BY - second priority)
                limit,
            ),
        )

        teams = [
            {
                "team_id": row[0],
                "name": row[1],
                "tag": row[2],
                "logo_url": row[3],
                "rating": row[4],
                "last_match_time": row[5],
            }
            for row in cursor.fetchall()
        ]

        return jsonify(teams), 200

    except Exception as e:
        logger.error(f"Error searching teams: {e!s}")
        return api_error(503, Errors.SEARCH_ERROR, e)

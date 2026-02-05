from dataclasses import dataclass
from typing import Any
from urllib import parse

from flask import request


@dataclass(frozen=True)
class ErrorDefinition:
    """Immutable error definition with code and default message."""

    code: str
    message: str


def error_response(
    error: ErrorDefinition | str, message: str | None = None, status_code: int = 400, **extra_details
) -> dict:
    """Create a standardized error response dict following REST API best practices.

    Args:
        error: ErrorDefinition instance or error code string (use ErrorCode constants)
        message: Optional message override (uses error.message if not provided)
        status_code: HTTP status code
        **extra_details: Additional key-value pairs to include in details

    Returns:
        Error dictionary ready for jsonify (return with status code separately)

    Example:
        # Using ErrorDefinition with default message:
        return jsonify(error_response(ErrorCode.MISSING_TEAMS, status_code=400)), 400

        # Overriding message:
        return jsonify(error_response(ErrorCode.MISSING_TEAMS, "Custom message", 400)), 400

        # Adding extra details:
        return jsonify(error_response(ErrorCode.TOO_MANY_TEAMS, status_code=400, limit=10)), 400
    """
    if isinstance(error, ErrorDefinition):
        code = error.code
        msg = message if message is not None else error.message
    else:
        code = error
        msg = message if message is not None else error

    details = {"url": request.path, **extra_details}
    return {"status": status_code, "code": code, "message": msg, "details": details}


# Error code constants (RFC 7807 compliant)
class Errors:
    """Standard error codes with human-readable messages for API responses."""

    COMPUTATION_ERROR = ErrorDefinition(
        "COMPUTATION_ERROR", "An unexpected error occurred during statistics computation"
    )
    FAILED_TO_FETCH_PRO_PLAYERS = ErrorDefinition("FAILED_TO_FETCH_PRO_PLAYERS", "Failed to fetch pro players from API")
    FAILED_TO_FETCH_TEAMS = ErrorDefinition("FAILED_TO_FETCH_TEAMS", "Failed to fetch teams from API")
    FAILED_TO_RETRIEVE_RESULTS = ErrorDefinition("FAILED_TO_RETRIEVE_RESULTS", "Failed to retrieve results")
    FAILED_TO_START_TASK = ErrorDefinition("FAILED_TO_START_TASK", "Failed to start background task")
    FAILED_TO_STORE_PRO_PLAYERS = ErrorDefinition(
        "FAILED_TO_STORE_PRO_PLAYERS", "Failed to store pro players to database"
    )
    FAILED_TO_STORE_TEAMS = ErrorDefinition("FAILED_TO_STORE_TEAMS", "Failed to store teams to database")
    INVALID_ACCOUNT_ID = ErrorDefinition("INVALID_ACCOUNT_ID", "Invalid account ID format")
    INVALID_REQUEST = ErrorDefinition("INVALID_REQUEST", "Invalid request")
    INVALID_TEAM_NAME = ErrorDefinition("INVALID_TEAM_NAME", "Invalid team name format")
    INVALID_TEAM_ID = ErrorDefinition("INVALID_TEAM_ID", "Team ID must be a non-negative integer")
    MISSING_ACCOUNT_IDS = ErrorDefinition("MISSING_ACCOUNT_IDS", "Account IDs are required")
    MISSING_TEAMS = ErrorDefinition("MISSING_TEAMS", "No teams provided")
    NETWORK_ERROR = ErrorDefinition("NETWORK_ERROR", "Failed to fetch data due to network error")
    RESULTS_NOT_FOUND = ErrorDefinition("RESULTS_NOT_FOUND", "Results not found")
    SEARCH_ERROR = ErrorDefinition("SEARCH_ERROR", "Database search failed")
    TOO_MANY_PLAYERS = ErrorDefinition("TOO_MANY_PLAYERS", "Too many players provided (maximum 10)")
    TOO_MANY_TEAMS = ErrorDefinition("TOO_MANY_TEAMS", "Too many teams (maximum 10)")
    UNEXPECTED_ERROR = ErrorDefinition("UNEXPECTED_ERROR", "An unexpected error occurred")
    UNSUPPORTED_METHOD = ErrorDefinition("UNSUPPORTED_METHOD", "HTTP method not supported")


def build_explorer_query(team: str | None = None, team_id: int | None = None) -> str:
    """Prepare SQL query to find team by name/tag or ID with rating info.

    Args:
        team: Team name or tag to search for (mutually exclusive with team_id)
        team_id: Team ID to search for (mutually exclusive with team)

    Returns:
        SQL query string with the team value embedded and properly escaped.

    Raises:
        ValueError: If neither or both parameters are provided, or if values are invalid
    """
    if (team is None and team_id is None) or (team is not None and team_id is not None):
        raise ValueError("Either 'team' or 'team_id' must be provided, but not both")

    if team_id is not None:
        # ID-based query: direct lookup by team_id
        if not isinstance(team_id, int) or team_id < 0:
            raise ValueError("Invalid team_id: must be a non-negative integer")

        sql = (
            "SELECT t.team_id, t.name, t.tag, tr.rating, tr.delta "
            "FROM teams t "
            "LEFT JOIN team_rating tr ON t.team_id = tr.team_id "
            f"WHERE t.team_id = {team_id} "
            "LIMIT 1"
        )
    else:
        # Name-based query: search by name or tag
        if not team or not isinstance(team, str):
            raise ValueError("Invalid team name")

        # Escape single quotes and backslashes for SQL
        escaped_team = team.replace("\\", "\\\\").replace("'", "''")

        sql = (
            "SELECT t.team_id, t.name, t.tag, tr.rating, tr.delta "
            "FROM teams t "
            "LEFT JOIN team_rating tr ON t.team_id = tr.team_id "
            f"WHERE t.name ILIKE '{escaped_team}' ESCAPE '\\' "
            f"OR t.tag ILIKE '{escaped_team}' ESCAPE '\\' "
            "ORDER BY tr.rating DESC "
            "LIMIT 1"
        )

    return sql


def get_percent_encoded_str(s: str) -> str:
    """URL-encode a string with all characters percent-encoded."""
    return parse.quote(s, safe="")


def get_team_id_from_explore_response(
    response_json: dict[str, Any],
) -> tuple[int, str, str, float | None, float | None]:
    """Extract team info from OpenDota explorer response JSON.

    Example response JSON:
    {"command": "SELECT",...,"rows": [ {"team_id": 1, "name": "aa", "tag": "a", "rating": 2500.5, "delta": 25.3}],
        "fields": [ { "name": "team_id",..., "format": "text"} ], }

    Returns:
        Tuple of (team_id, name, tag, rating, delta)
    """
    response_preview = str(response_json)[:300]

    if "command" not in response_json or response_json["command"] != "SELECT":
        raise ValueError(f"Unexpected command in response. Response preview: {response_preview}")

    if "rows" not in response_json or not response_json["rows"]:
        raise ValueError(f"No rows in response. Response preview: {response_preview}")
    if len(response_json["rows"]) != 1:
        raise ValueError(f"Unexpected number of rows in response. Response preview: {response_preview}")
    row = response_json["rows"][0]

    if (
        "team_id" not in row
        or not isinstance(row["team_id"], int)
        or "name" not in row
        or not isinstance(row["name"], str)
        or "tag" not in row
        or not isinstance(row["tag"], str)
    ):
        raise ValueError(
            f"team_id, name, or tag cannot be found in the row {row}. Response preview: {response_preview}"
        )

    rating = row.get("rating")
    delta = row.get("delta")

    # Ensure rating and delta are floats or None
    if rating is not None and not isinstance(rating, (int, float)):
        rating = None
    if delta is not None and not isinstance(delta, (int, float)):
        delta = None

    return row["team_id"], row["name"], row["tag"], rating, delta

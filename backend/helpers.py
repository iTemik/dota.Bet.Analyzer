from typing import Any
from urllib import parse


# Error code constants (RFC 7807 compliant)
class ErrorCode:
    """Machine-readable error codes for API responses."""

    MISSING_ACCOUNT_IDS = "MISSING_ACCOUNT_IDS"
    TOO_MANY_PLAYERS = "TOO_MANY_PLAYERS"
    INVALID_ACCOUNT_ID = "INVALID_ACCOUNT_ID"
    FAILED_TO_START_TASK = "FAILED_TO_START_TASK"
    INVALID_REQUEST = "INVALID_REQUEST"
    RESULTS_NOT_FOUND = "RESULTS_NOT_FOUND"
    FAILED_TO_RETRIEVE_RESULTS = "FAILED_TO_RETRIEVE_RESULTS"
    MISSING_TEAMS = "MISSING_TEAMS"
    UNSUPPORTED_METHOD = "UNSUPPORTED_METHOD"
    TOO_MANY_TEAMS = "TOO_MANY_TEAMS"
    FAILED_TO_FETCH_PRO_PLAYERS = "FAILED_TO_FETCH_PRO_PLAYERS"
    FAILED_TO_STORE_PRO_PLAYERS = "FAILED_TO_STORE_PRO_PLAYERS"
    FAILED_TO_FETCH_TEAMS = "FAILED_TO_FETCH_TEAMS"
    FAILED_TO_STORE_TEAMS = "FAILED_TO_STORE_TEAMS"


def prepare_sql_for_team_explore(team: str) -> str:
    """Prepare SQL query to find team by name or tag with rating info.

    Args:
        team: Team name or tag to search for

    Returns:
        SQL query string with the team value embedded and properly escaped.

    Raises:
        ValueError: If team name is invalid
    """
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

from typing import Any
from urllib import parse


def prepare_sql_for_team_explore(team: str) -> str:
    """Prepare SQL query to find team by name or tag.

    Args:
        team: Team name or tag to search for

    Returns:
        SQL query string with sanitized team name

    Raises:
        ValueError: If team name is invalid
    """
    if not team or not isinstance(team, str):
        raise ValueError("Invalid team name")
    team = team.strip()
    # Sanitize team name for SQL usage: escape backslashes, wildcard characters, and single quotes
    sanitized_team = (
        team.replace("\\", "\\\\")  # escape backslash itself
        .replace("%", "\\%")  # escape SQL wildcard %
        .replace("_", "\\_")  # escape SQL wildcard _
        .replace("'", "''")  # escape single quote for SQL string literal
    )

    # SQL query example:
    #   SELECT team_id, name, tag FROM teams
    #   WHERE ( name ILIKE '<team>' ESCAPE '\' OR tag  ILIKE '<team>' ESCAPE '\' )
    #   AND tag <> '' LIMIT 1;

    sql = (
        f"SELECT team_id, name, tag FROM teams "
        f"WHERE ( name ILIKE '{sanitized_team}' ESCAPE '\\'"
        f" OR tag  ILIKE '{sanitized_team}' ESCAPE '\\' ) AND tag <> '' LIMIT 1;"
    )
    return sql


def get_percent_encoded_str(s: str) -> str:
    """URL-encode a string with all characters percent-encoded."""
    return parse.quote(s, safe="")


def get_team_id_from_explore_response(response_json: dict[str, Any]) -> tuple[int, str, str]:
    """Extract team_id from OpenDota explorer response JSON.

    Example response JSON:
    {"command": "SELECT",...,"rows": [ {"team_id": 1, "name": "aa", "tag": "a"}],
        "fields": [ { "name": "team_id",..., "format": "text"} ], }
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

    return row["team_id"], row["name"], row["tag"]

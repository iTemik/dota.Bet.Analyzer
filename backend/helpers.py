from dataclasses import dataclass
from typing import Any, Optional
from urllib import parse

from flask import Response, jsonify, request
from pydantic import BaseModel, Field


@dataclass(frozen=True)
class ErrorDefinition:
    """Immutable error definition with code and default message."""

    code: str
    message: str


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


class ApiError(BaseModel):
    """API error information following REST API best practices.

    Provides consistent error reporting across different response models.
    Can be instantiated directly to represent API errors.

    Attributes:
        status: HTTP status code (e.g., 400, 404, 500)
        code: Machine-readable error code (e.g., NETWORK_ERROR, HTTP_ERROR)
        message: Human-readable error message
        details: Additional error context as a dictionary (e.g., {"url": "..."})
    """

    status: Optional[int] = Field(default=None, description="HTTP status code")
    code: Optional[str] = Field(default=None, description="Machine-readable error code")
    message: Optional[str] = Field(default=None, description="Human-readable error message")
    details: Optional[dict] = Field(default=None, description="Additional error context")

    @classmethod
    def of(cls, error: ErrorDefinition, status: int, **details: Any) -> "ApiError":
        """Create an ApiError from an Errors definition.

        Args:
            error: ErrorDefinition from Errors
            status: HTTP status code
            **details: Additional error context

        Returns:
            ApiError with the definition's code and message
        """
        return cls(status=status, code=error.code, message=error.message, details=details)

    @staticmethod
    def create_response(
        status: int,
        *,
        error: Optional[ErrorDefinition] = None,
        code: Optional[str] = None,
        message: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> tuple[Response, int]:
        """Create a jsonified error response (Flask Response, status_code tuple).

        Args:
            status: HTTP status code
            error: ErrorDefinition from helpers (mutually exclusive with code)
            code: Machine-readable error code string (mutually exclusive with error)
            message: Human-readable error message (required with code, optional with error)
            details: Optional additional error context

        Returns:
            Tuple of (Flask Response with JSON, status code)

        Raises:
            ValueError: If both error and code are provided, or neither is provided

        Examples:
            # Using ErrorDefinition from helpers
            return ApiError.create_response(400, error=Errors.MISSING_TEAMS, details={"url": request.path})

            # Using ErrorDefinition with custom message override:
            return ApiError.create_response(400, error=Errors.INVALID_TEAM_NAME, message="Custom message")

            # Using string code and message:
            return ApiError.create_response(400, code="CUSTOM_ERROR", message="Something went wrong")
        """
        # Validate mutually exclusive parameters
        if error is not None and code is not None:
            raise ValueError("Cannot specify both 'error' and 'code' parameters")

        if error is None and code is None:
            raise ValueError("Must specify either 'error' or 'code' parameter")

        # Extract code and message based on parameter type
        if error is not None:
            error_code: str = error.code
            error_message: str = message if message is not None else error.message
        else:
            if message is None:
                raise ValueError("'message' is required when using 'code' parameter")
            if code is None:
                raise ValueError("Must specify either 'error' or 'code' parameter")
            error_code = code
            error_message = message

        return (
            jsonify(
                {
                    "status": status,
                    "code": error_code,
                    "message": error_message,
                    "details": details or {},
                }
            ),
            status,
        )


def api_error(
    status: int, error: ErrorDefinition, exc: Optional[BaseException] = None, **details: Any
) -> tuple[Response, int]:
    """Jsonified error response for the current request; adds `url` (and `exception` when exc is given) to details.

    Args:
        status: HTTP status code
        error: ErrorDefinition from Errors
        exc: Exception that caused the error (optional)
        **details: Additional error context

    Returns:
        Tuple of (Flask Response with JSON, status code)
    """
    details = {"url": request.path, **details}
    if exc is not None:
        details["exception"] = str(exc)
    return ApiError.create_response(status, error=error, details=details)


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


class ExplorerTeam(BaseModel):
    """Team found by the OpenDota explorer query from build_explorer_query.

    Attributes:
        team_id: Team identifier
        name: Team name
        tag: Team tag
        rating: Team rating (None if unknown)
        delta: Latest rating change (None if unknown)
    """

    team_id: int
    name: str
    tag: str
    rating: Optional[float] = None
    delta: Optional[float] = None

    @classmethod
    def from_response(cls, response_json: dict[str, Any]) -> "ExplorerTeam":
        """Create from an OpenDota explorer response JSON.

        Example response JSON:
        {"command": "SELECT",...,"rows": [ {"team_id": 1, "name": "aa", "tag": "a", "rating": 2500.5, "delta": 25.3}],
            "fields": [ { "name": "team_id",..., "format": "text"} ], }

        Raises:
            ValueError: If the response is not a single valid team row
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
            not isinstance(row.get("team_id"), int)
            or not isinstance(row.get("name"), str)
            or not isinstance(row.get("tag"), str)
        ):
            raise ValueError(
                f"team_id, name, or tag cannot be found in the row {row}. Response preview: {response_preview}"
            )

        # Rating and delta that are not numbers are treated as unknown
        rating, delta = row.get("rating"), row.get("delta")
        return cls(
            team_id=row["team_id"],
            name=row["name"],
            tag=row["tag"],
            rating=rating if isinstance(rating, (int, float)) else None,
            delta=delta if isinstance(delta, (int, float)) else None,
        )

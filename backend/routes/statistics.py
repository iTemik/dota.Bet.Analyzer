"""Compare routes: team statistics, the player statistics task, its progress stream and results."""

import json
import time

from flask import Response, jsonify, request, stream_with_context

from backend.helpers import Errors, api_error
from backend.logging_config import setup_logging
from backend.routes import ApiBlueprint
from backend.schemas import (
    PlayerStatisticsQuerySchema,
    StatisticsResultSchema,
    StatsResponseSchema,
    TaskResponseSchema,
    TeamStatisticsQuerySchema,
)
from backend.stats import compute_statistics
from backend.task_store import (
    load_results,
    progress_exists,
    read_progress,
    start_task,
    subscribe_progress,
    wait_for_progress,
)
from backend.tasks import players_statistics_task

logger = setup_logging(__name__)

bp = ApiBlueprint("Statistics", __name__, description="Team comparison: statistics, player task, progress, results")


def _parse_team_ids_from_args(team_ids: list) -> tuple[list[int], tuple[Response, int] | None]:
    """Parse and validate team IDs from query arguments.

    Args:
        team_ids: List of team ID values from query parameters

    Returns:
        Tuple of (parsed_team_ids_int, error_response) where:
        - parsed_team_ids_int is the list of validated integer team IDs
        - error_response is an api_error response tuple if validation failed, None otherwise
    """
    team_ids_int: list[int] = []
    for tid in team_ids:
        value = tid.strip() if isinstance(tid, str) else tid
        if value is None or value == "":
            continue
        if isinstance(value, int):
            team_ids_int.append(value)
        elif isinstance(value, str) and value.isdigit():
            team_ids_int.append(int(value))
        else:
            # Not a number, or an unsupported type
            return [], api_error(422, Errors.INVALID_REQUEST, invalid_team_id=tid)

    return team_ids_int, None


@bp.route("/statistics", methods=["GET"])
@bp.arguments(TeamStatisticsQuerySchema, location="query")
@bp.response(200, StatsResponseSchema)
@bp.error_response(400, Errors.INVALID_REQUEST, "Invalid request")
@bp.error_response(
    422, Errors.MISSING_TEAMS, "Validation failed - missing teams, too many teams (>10), or invalid parameter format"
)
@bp.error_response(500, Errors.COMPUTATION_ERROR, "Computation failed")
def statistics(args) -> tuple[Response, int]:
    """Compute team statistics.

    Query parameters:
    - team_id: Team ID (supports multiple values: `?team_id=123&team_id=456`)
    - team: Team name (supports multiple values: `?team=Alpha&team=Beta`)
    - team1, team2, ...: Alternative numbered format

    Returns computed statistics for the specified teams (1-10 teams combined).
    Includes team ratings, tags, IDs, rating deltas, player lists, and a `task_id`
    for asynchronous player statistics computation.
    """
    try:
        # Get team IDs
        team_ids = args.get("team_id", []) if args else []
        team_ids_int, parse_error = _parse_team_ids_from_args(team_ids)
        if parse_error:
            return parse_error

        # Get team names
        teams = args.get("team", []) if args else []
        if not teams:
            teams = [v for k, v in sorted(request.args.items()) if k.startswith("team") and not k.endswith("_id")]

        # Normalize team names
        teams = [t.strip() for t in teams if isinstance(t, str) and t.strip()]

        # Validate at least one is provided
        if not teams and not team_ids_int:
            return api_error(422, Errors.MISSING_TEAMS)

        # Validate total count doesn't exceed limit
        total_teams = len(teams) + len(team_ids_int)
        if total_teams > 10:
            return api_error(422, Errors.TOO_MANY_TEAMS, limit=10)

        # Compute statistics with both lists
        stats = compute_statistics(
            teams=teams if teams else None,
            team_ids=team_ids_int if team_ids_int else None,
            days=args.get("days", 20),
        )
        return jsonify(stats.model_dump()), 200

    except ValueError as e:
        logger.error(f"Validation error in compute_statistics: {e}")
        return api_error(400, Errors.INVALID_REQUEST, e)
    except Exception as e:
        logger.error(f"Unexpected error in statistics computation: {e}", exc_info=True)
        return api_error(500, Errors.COMPUTATION_ERROR, e)


@bp.route("/statistics/players", methods=["GET"])
@bp.arguments(PlayerStatisticsQuerySchema, location="query")
@bp.response(
    200,
    TaskResponseSchema,
    description="Task started successfully",
    example={"status": "started", "task_id": "task_3f9c2a7e5b8d4c1fa6e0b2d9c4f7a813", "celery_task_id": "abc-123-def"},
)
@bp.error_response(400, Errors.INVALID_REQUEST, "Invalid request parameters")
@bp.error_response(422, Errors.VALIDATION_ERROR, "Schema validation failed")
@bp.error_response(500, Errors.FAILED_TO_START_TASK, "Task start failed")
def players_statistics(args) -> tuple[Response, int]:
    """Start asynchronous player statistics computation task.

    Initiates a background task to fetch and analyze match history for the specified players.
    The computation typically takes 10-20 seconds as it collects individual match statistics
    for each team player from the OpenDota API.

    Account List Sources:
        The account list can be populated in two ways:
        1. **Direct Frontend Call**: Account IDs passed directly via query parameters
           (`GET /api/statistics/players?account_id=123&account_id=456`)
        2. **Indirect via Team Statistics**: Account IDs gathered from `compute_statistics()`
           which fetches team data and calls `_create_team_stats()` -> `get_players_by_team()`
           to extract player account IDs from team roster data
           (`GET /api/statistics?team=Alliance` internally triggers player stats collection)

    Query Parameters:
        - `account_id`: List of player account IDs (1-10 players, required)
        - `days`: Number of days of match history to analyze (1-365, default: 20)

    Returns:
        TaskResponseSchema containing `status`, `task_id` for progress tracking, and `celery_task_id`

    Workflow:

        1. Call this endpoint to start the task → receive `task_id`
        2. Monitor progress via `/api/stream-progress/{task_id}` (Server-Sent Events)
        3. Retrieve final results via `/api/results/{task_id}` once complete


    Example:
        `GET /api/statistics/players?account_id=12345&account_id=67890&days=30`

        Response (200):

        {
            "status": "started",
            "task_id": "task_3f9c2a7e5b8d4c1fa6e0b2d9c4f7a813",
            "celery_task_id": "abc-123-def-456"
        }

    """
    try:
        accounts = args["account_id"]
        days = args.get("days", 20)

        # Schema already validates: 1-10 accounts, valid integers, days 1-365
        # Convert to int list if needed
        accounts_int = [int(a) if not isinstance(a, int) else a for a in accounts]

        try:
            task_id, celery_task_id = start_task(players_statistics_task, accounts=accounts_int, days=days)
            return jsonify({"status": "started", "task_id": task_id, "celery_task_id": celery_task_id}), 200
        except Exception as e:
            return api_error(500, Errors.FAILED_TO_START_TASK, e)

    except Exception as e:
        return api_error(400, Errors.INVALID_REQUEST, e)


def _create_error_message(message: str, timeout: bool = False) -> str:
    """Create formatted error message for SSE stream.

    Args:
        message: Error message text
        timeout: Whether this is a timeout error

    Returns:
        JSON-formatted error message string
    """
    error_msg = {
        "step": -1,
        "message": message,
        "progress": -1,
        "data": {"error": True, "timeout": timeout} if timeout else {"error": True},
    }
    return f"{json.dumps(error_msg)}\n"


# Progress stream limits (seconds). A stream that ends early is reopened by the client.
STREAM_MAX_RUNTIME = 120
STREAM_IDLE_TIMEOUT = 30
# Safety net: re-read the snapshot this often even if a progress signal is missed
STREAM_RECHECK_INTERVAL = 1.0


def _check_timeouts(start_time: float, last_update_time: float) -> str | None:
    """Check for timeout conditions.

    Args:
        start_time: Stream start time (time.monotonic)
        last_update_time: Time of the last sent update (time.monotonic)

    Returns:
        Error message string if timeout occurred, None otherwise
    """
    now = time.monotonic()
    if now - start_time > STREAM_MAX_RUNTIME:
        return _create_error_message(f"Task exceeded maximum runtime ({STREAM_MAX_RUNTIME}s)", timeout=True)

    if now - last_update_time > STREAM_IDLE_TIMEOUT:
        return _create_error_message(f"Task timed out - no progress updates for {STREAM_IDLE_TIMEOUT}s", timeout=True)

    return None


def _generate_progress_stream(task_id: str):
    """Generate progress updates stream for a task.

    Sends the task's progress snapshot from Redis each time it changes, until the task
    reaches completion or an error state. Between changes it waits for the task's
    progress signal instead of polling Redis.

    Args:
        task_id: Task identifier

    Yields:
        JSON-formatted progress updates or error messages
    """
    start_time = time.monotonic()
    last_update_time = start_time
    last_sent: bytes | None = None
    subscription = None

    try:
        # Subscribe before the first read, so a change between the two is not missed
        subscription = subscribe_progress(task_id)
        while True:
            snapshot = read_progress(task_id)
            if snapshot is not None and snapshot != last_sent:
                progress_data = json.loads(snapshot)
                yield f"{json.dumps(progress_data)}\n"
                last_sent = snapshot
                last_update_time = time.monotonic()
                if progress_data["progress"] >= 100 or progress_data["progress"] == -1:
                    return

            timeout_error = _check_timeouts(start_time, last_update_time)
            if timeout_error:
                yield timeout_error
                return

            wait_for_progress(subscription, STREAM_RECHECK_INTERVAL)

    except json.JSONDecodeError as e:
        yield _create_error_message(f"Invalid progress data: {e}")
    except Exception as e:
        yield _create_error_message(f"Stream error: {e}")
    finally:
        if subscription is not None:
            subscription.close()


@bp.route("/stream-progress/<task_id>")
@bp.response(200, description="Server-Sent Events stream of progress updates")
@bp.error_response(404, Errors.RESULTS_NOT_FOUND, "Task not found", task_id="task_123")
@bp.error_response(500, Errors.FAILED_TO_RETRIEVE_RESULTS, "Redis connection error")
def stream_progress(task_id: str) -> tuple[Response, int] | Response:
    """Stream progress updates via Server-Sent Events.

    Returns a continuous stream of progress data for the specified task, one JSON object
    per line, sent as soon as the task's progress changes. The stream ends when the task
    completes (100) or fails (-1), or with a timeout line after 30s without changes or 120s
    in total; clients reopen it until the task completes.

    Path Parameters:
        - `task_id`: Task identifier returned from `/api/statistics/players`

    Returns:
        Server-Sent Events stream with progress updates (200) or error response (404, 500)

    Example:
        `GET /api/stream-progress/task_3f9c2a7e5b8d4c1fa6e0b2d9c4f7a813`

        Stream (200):

        {"step": 1, "message": "Fetching matches...", "progress": 25, "data": {...}}
        {"step": 2, "message": "Processing...", "progress": 50, "data": {...}}
        {"step": 3, "message": "Completed", "progress": 100, "data": {...}}

    """
    # Verify task exists before starting stream
    try:
        if not progress_exists(task_id):
            return api_error(404, Errors.RESULTS_NOT_FOUND, task_id=task_id)
    except Exception as e:
        logger.error(f"Redis error checking task {task_id}: {e}")
        return api_error(500, Errors.FAILED_TO_RETRIEVE_RESULTS, e)

    return Response(
        stream_with_context(_generate_progress_stream(task_id)),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "Access-Control-Allow-Origin": "*"},
    )


@bp.route("/results/<task_id>")
@bp.response(200, StatisticsResultSchema)
@bp.error_response(404, Errors.RESULTS_NOT_FOUND, "Results not found", task_id="task_123")
@bp.error_response(500, Errors.FAILED_TO_RETRIEVE_RESULTS, "Failed to retrieve results")
def get_results(task_id: str) -> tuple[Response, int]:
    """Retrieve final computation results for a completed task.

    Returns the complete results of a background player statistics computation task.
    Results include detailed match statistics, player performance metrics, and aggregated summaries.

    Path Parameters:
        - `task_id`: Task identifier returned from `/api/statistics/players`

    Returns:
        **StatisticsResultSchema** with complete results (200), or error response (404, 500)


    Workflow:

        1. Start task via `/api/statistics/players` → receive `task_id`
        2. Monitor progress via `/api/stream-progress/{task_id}` until complete
        3. Retrieve results via this endpoint once task reaches 100% progress


    Results include:

        - Per-player match statistics (wins, losses, hero picks, performance metrics)
        - Team summary statistics (average rank, win rates, common heroes)
        - Error details for any failed player data fetches


    Notes:

        - Results expire after 1 hour (Redis TTL)
        - Returns 404 if task not found, expired, or still in progress
        - Results only available after task completion (progress = 100%)


    Example:
        `GET /api/results/task_3f9c2a7e5b8d4c1fa6e0b2d9c4f7a813`

        Response (200):
        {
            "results": [...],
            "successful": 5,
            "total": 5,
            "summary": {...}
        }

    """
    try:
        results = load_results(task_id)
        if results is None:
            return api_error(404, Errors.RESULTS_NOT_FOUND, task_id=task_id)

        return jsonify(results), 200
    except Exception as e:
        logger.error(f"Error retrieving results for task {task_id}: {e}")
        return api_error(500, Errors.FAILED_TO_RETRIEVE_RESULTS, e)

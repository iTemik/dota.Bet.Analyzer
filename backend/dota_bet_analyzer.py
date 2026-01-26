import json
import os
import time

import redis
from celery import Celery  # type: ignore[import-untyped]
from flask import Response, jsonify, request, stream_with_context
from flask_smorest import Blueprint

from backend import __version__
from backend.config import Config
from backend.helpers import Errors
from backend.logging_config import setup_logging
from backend.pro_players import (
    fetch_pro_players_from_api,
    fetch_teams_from_api,
    store_pro_players,
    store_teams,
)
from backend.schemas import (
    ErrorSchema,
    PlayerStatisticsQuerySchema,
    StatisticsResultSchema,
    StatsResponseSchema,
    SyncResponseSchema,
    TaskResponseSchema,
    TeamSchema,
    TeamSearchQuerySchema,
    TeamStatisticsQuerySchema,
    VersionSchema,
)
from backend.stats import (
    ApiError,
    compute_statistics,
    get_matches,
    get_rank,
    get_team_matches_summary,
)

# Setup logger
logger = setup_logging(__name__)


bp = Blueprint("dota", __name__, url_prefix="/api", description="Dota 2 Bet Analyzer API")

# Initialize Celery without app-specific config; the app factory will update it
celery = Celery(__name__)

# Configure Celery to use Redis as message broker (development)
# Redis connection: redis://localhost:6379/0
celery.conf.update(
    broker_url=f"redis://{Config.REDIS_HOST}:{Config.REDIS_PORT}/0",
    result_backend=f"redis://{Config.REDIS_HOST}:{Config.REDIS_PORT}/0",
)

# Redis for progress storage
redis_client = redis.Redis(host=Config.REDIS_HOST, port=Config.REDIS_PORT, db=1)


def update_progress(task_id: str, step: int, message: str, progress: float, data: dict | None = None) -> None:
    """Update task progress in Redis (lightweight - no heavy data).

    Args:
        task_id: Unique task identifier
        step: Current step number
        message: Progress message
        progress: Progress percentage (0-100) or -1 for error
        data: Additional data to store (optional, should be lightweight)
    """
    try:
        progress_data = {
            "step": step,
            "message": message,
            "progress": progress,
            "data": data or {},
            "timestamp": time.time(),
        }
        redis_client.setex(f"progress:{task_id}", 3600, json.dumps(progress_data))  # Expire after 1 hour
        logger.debug(f"Progress updated for task {task_id}: {message} ({progress}%)")
    except Exception as e:
        # Log error but don't fail the task if Redis is unavailable
        logger.warning(f"Failed to update progress for task {task_id}: {e}")


def store_results(task_id: str, results_data: dict) -> None:
    """Store heavy computation results in Redis (separate from progress).

    Args:
        task_id: Unique task identifier
        results_data: Heavy results data (will be stored separately)
    """
    try:
        redis_client.setex(f"results:{task_id}", 3600, json.dumps(results_data))  # Expire after 1 hour
        logger.debug(f"Results stored for task {task_id}")
    except Exception as e:
        logger.warning(f"Failed to store results for task {task_id}: {e}")


@celery.task(bind=True)
def players_statistics_task(self, task_id, accounts: list[int], days: int = 20):
    """Celery task to fetch match statistics for multiple players.

    Args:
        task_id: Unique task identifier for progress tracking
        accounts: List of account IDs to fetch statistics for
        days: Number of days of match history to fetch
    """
    try:
        logger.info(f"Starting players_statistics_task: task_id={task_id}, accounts={accounts}, days={days}")
        steps: int = 2 + 2 * len(accounts)  # Initial + per-account + final
        step_num: int = 0

        update_progress(
            task_id,
            step_num,
            f"Initializing match history fetch for {len(accounts)} players",
            100 * (step_num / steps),
        )

        results = []
        matches_stats = []  # List of lists: each inner list is matches for one player
        bad_rank_players: int = 0
        players_avg_rank: float = 0.0
        players_with_rank: int = 0
        for account_id in accounts:
            step_num += 1
            try:
                # Fetch match data for this account
                players_statistics = get_matches(account_id=account_id, days=days)
                matches_stats.append(players_statistics)  # Append as a list per player

                # Convert MatchStats objects to dicts for JSON serialization
                stats_data = [stat.model_dump() for stat in players_statistics]

                # TODO: rework, why do we need these results?
                results.append(
                    {
                        "account_id": account_id,
                        "match_count": len(stats_data),
                        "matches": stats_data,
                    }
                )

                update_progress(
                    task_id,
                    step_num,
                    f"Fetched {len(stats_data)} matches for account {account_id}",
                    100 * (step_num / steps),
                    {"account_id": account_id, "match_count": len(stats_data)},
                )

                player_rank = get_rank(account_id)
                if player_rank is not None:
                    players_with_rank += 1
                    players_avg_rank += player_rank
                    if player_rank > 1000:  # Tysyachniks ruin the games.
                        bad_rank_players += 1
                        logger.info(f"Account {account_id} is tysyachnik and will ruin the games for high rank players")

                update_progress(
                    task_id,
                    step_num,
                    f"Got Player rank {player_rank} for account {account_id}",
                    100 * (step_num / steps),
                    {"account_id": account_id, "player_rank": player_rank},
                )

            except Exception as e:
                # Handle per-account errors gracefully
                # TODO: rework, why do we need these results?
                results.append(
                    {
                        "account_id": account_id,
                        "error": str(e),
                    }
                )

                update_progress(
                    task_id,
                    step_num,
                    f"Error fetching data for account {account_id}: {e!s}",
                    100 * (step_num / steps),
                    {"account_id": account_id, "error": str(e)},
                )

            time.sleep(0.01)  # Short sleep to prevent overwhelming the API
        players_avg_rank /= players_with_rank if players_with_rank else 1
        step_num += 1  # Final summary
        summary = get_team_matches_summary(matches_stats)  # This is heavy logic. To check.
        summary.avg_rank = players_avg_rank
        summary.bad_rank_players = bad_rank_players

        successful = len([r for r in results if "error" not in r])

        # Store heavy results separately (not in progress stream)
        final_results = {
            "results": results,
            "successful": successful,
            "total": len(accounts),
            "summary": summary.model_dump(),
        }
        store_results(task_id, final_results)

        # Update progress with lightweight final message (no heavy data)
        update_progress(
            task_id,
            steps,
            f"Completed: fetched data for {successful}/{len(accounts)} players",
            100,
            {"successful": successful, "total": len(accounts)},  # Lightweight summary only
        )

    except Exception as exc:
        logger.error(f"Task error for task_id={task_id}: {exc}", exc_info=True)
        update_progress(task_id, -1, f"Task error: {exc!s}", -1, {"error": True})
        raise


@bp.route("/version", methods=["GET"])
@bp.response(200, VersionSchema)
def get_version() -> tuple[Response, int]:
    """Get backend version.

    Returns backend version including build number.

    This endpoint always succeeds and returns 200 OK.
    """
    backend_version = __version__
    build_number = os.environ.get("BUILD_NUMBER", "DEV")
    full_backend_version = f"{backend_version}.{build_number}"

    return (
        jsonify(
            {
                "backend": full_backend_version,
                "build": build_number,
            }
        ),
        200,
    )


@bp.route("/statistics", methods=["GET"])
@bp.arguments(TeamStatisticsQuerySchema, location="query")
@bp.response(200, StatsResponseSchema)
@bp.alt_response(
    400,
    schema=ErrorSchema,
    description="Invalid parameters",
    example={
        "status": 400,
        "code": "MISSING_TEAMS",
        "message": "No teams provided",
        "details": {"url": "/api/statistics"},
    },
)
@bp.alt_response(
    422,
    schema=ErrorSchema,
    description="Validation failed",
    example={
        "status": 422,
        "code": "VALIDATION_ERROR",
        "message": "Invalid team parameter format",
        "details": {"url": "/api/statistics"},
    },
)
@bp.alt_response(
    500,
    schema=ErrorSchema,
    description="Computation failed",
    example={
        "status": 500,
        "code": "COMPUTATION_ERROR",
        "message": "An unexpected error occurred during statistics computation",
        "details": {"url": "/api/statistics", "exception": "Database connection failed"},
    },
)
def statistics(args) -> tuple[Response, int]:
    """Compute team statistics.

    Query parameters:
    - team: Team name (supports multiple values: `?team=Alpha&team=Beta`)
    - team1, team2, ...: Alternative numbered format (legacy support)

    Returns computed statistics for the specified teams (1-10 teams).
    Includes team ratings, tags, IDs, rating deltas, player lists, and a `task_id`
    for asynchronous player statistics computation.
    """
    # Get teams from validated args or fall back to legacy numbered format
    teams = args.get("team", []) if args else []
    if not teams:
        teams = [v for k, v in sorted(request.args.items()) if k.startswith("team")]

    # Normalize & validate
    teams = [t.strip() for t in teams if isinstance(t, str) and t.strip()]
    if not teams:
        return ApiError.create_response(400, error=Errors.MISSING_TEAMS, details={"url": request.path})
    if len(teams) > 10:
        return ApiError.create_response(400, error=Errors.TOO_MANY_TEAMS, details={"url": request.path, "limit": 10})

    # Wrap compute_statistics in try-except to handle unexpected errors
    # Possible failures: database connection issues, Celery/Redis failures, unexpected exceptions
    try:
        stats = compute_statistics(teams)
        return jsonify(stats.model_dump()), 200
    except ValueError as e:
        # Should not happen with current validation, but handle it defensively
        logger.error(f"Validation error in compute_statistics: {e}")
        return ApiError.create_response(
            400, error=Errors.INVALID_REQUEST, details={"url": request.path, "exception": str(e)}
        )
    except Exception as e:
        # Catch unexpected errors (database failures, network issues, etc.)
        logger.error(f"Unexpected error in statistics computation: {e}", exc_info=True)
        return ApiError.create_response(
            500,
            error=Errors.COMPUTATION_ERROR,
            details={"url": request.path, "exception": str(e)},
        )


@bp.route("/statistics/players", methods=["GET"])
@bp.arguments(PlayerStatisticsQuerySchema, location="query")
@bp.response(
    200,
    TaskResponseSchema,
    description="Task started successfully",
    example={"status": "started", "task_id": "task_<team_id>_1234567890", "celery_task_id": "abc-123-def"},
)
@bp.alt_response(
    400,
    schema=ErrorSchema,
    description="Invalid request parameters",
    example={
        "status": 400,
        "code": "INVALID_REQUEST",
        "message": "Invalid request",
        "details": {"url": "/api/statistics/players", "exception": "Invalid account_id format"},
    },
)
@bp.alt_response(
    422,
    schema=ErrorSchema,
    description="Schema validation failed",
    example={
        "status": 422,
        "code": "VALIDATION_ERROR",
        "message": "Invalid parameter: account_id must be between 1 and 10 items",
        "details": {"url": "/api/statistics/players"},
    },
)
@bp.alt_response(
    500,
    schema=ErrorSchema,
    description="Task start failed",
    example={
        "status": 500,
        "code": "FAILED_TO_START_TASK",
        "message": "Failed to start background task",
        "details": {
            "url": "/api/statistics/players",
            "task_id": "task_1234567890",
            "exception": "Celery connection failed",
        },
    },
)
def players_statistics(args) -> tuple[Response, int]:
    """Start asynchronous player statistics computation task.

    Initiates a background task to fetch and analyze match history for the specified players.
    The computation typically takes 10-20 seconds as it collects individual match statistics
    for each team player from the OpenDota API.

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
            "task_id": "task_1234567890",
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
            task = players_statistics_task.delay(
                task_id := f"task_{int(time.time())}", accounts=accounts_int, days=days
            )
            return jsonify({"status": "started", "task_id": task_id, "celery_task_id": task.id}), 200
        except Exception as e:
            return ApiError.create_response(
                500,
                error=Errors.FAILED_TO_START_TASK,
                details={"task_id": task_id, "url": request.path, "exception": str(e)},
            )

    except Exception as e:
        return ApiError.create_response(
            400, error=Errors.INVALID_REQUEST, details={"url": request.path, "exception": str(e)}
        )


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


def _check_timeouts(start_time: float, no_update_count: int, max_runtime: int, max_no_update: int) -> str | None:
    """Check for timeout conditions.

    Args:
        start_time: Task start timestamp
        no_update_count: Number of iterations without progress
        max_runtime: Maximum runtime in seconds
        max_no_update: Maximum iterations without update

    Returns:
        Error message string if timeout occurred, None otherwise
    """
    if time.time() - start_time > max_runtime:
        return _create_error_message(f"Task exceeded maximum runtime ({max_runtime}s)", timeout=True)

    if no_update_count >= max_no_update:
        return _create_error_message(f"Task timed out - no progress updates for {max_no_update * 0.01}s", timeout=True)

    return None


def _generate_progress_stream(task_id: str):
    """Generate progress updates stream for a task.

    Reads lightweight progress snapshots from Redis and emits them
    until the task reaches completion or an error state.

    Args:
        task_id: Task identifier

    Yields:
        JSON-formatted progress updates or error messages

    Safety mechanisms:
    - Max iterations: 6000 (60 seconds at 0.01s sleep)
    - Timeout on no updates: 300 iterations (3 seconds)
    - Max runtime: 120 seconds absolute limit
    """
    last_step = 0
    no_update_count = 0
    max_no_update = 300  # 3 seconds at 0.01s sleep
    max_iterations = 6000  # 60 seconds at 0.01s sleep
    max_runtime = 120  # 2 minutes absolute limit
    start_time = time.time()

    for _ in range(max_iterations):
        # Check for timeout conditions
        timeout_error = _check_timeouts(start_time, no_update_count, max_runtime, max_no_update)
        if timeout_error:
            yield timeout_error
            return

        try:
            # Process progress data
            progress_data, last_step, is_complete = _process_progress_data(task_id, last_step)

            # No new progress
            if progress_data is None:
                no_update_count += 1
                time.sleep(0.01)
                continue

            # Send progress update
            yield f"{json.dumps(progress_data)}\n"
            no_update_count = 0

            # Check for completion
            if is_complete:
                return

            time.sleep(0.01)

        except json.JSONDecodeError as e:
            yield _create_error_message(f"Invalid progress data: {e}")
            return
        except Exception as e:
            yield _create_error_message(f"Stream error: {e}")
            return

    # Max iterations reached without completion
    yield _create_error_message(f"Stream exceeded maximum iterations ({max_iterations})", timeout=True)


def _process_progress_data(task_id: str, last_step: int) -> tuple[dict | None, int, bool]:
    """Process progress data from Redis.

    Args:
        task_id: Task identifier
        last_step: Last processed step number

    Returns:
        Tuple of (progress_data, new_last_step, is_complete)
        - progress_data: Parsed JSON data or None if no progress
        - new_last_step: Updated last step value
        - is_complete: True if task is complete or errored
    """
    try:
        progress_bytes = redis_client.get(f"progress:{task_id}")
        if not progress_bytes:
            return None, last_step, False

        progress_data = json.loads(progress_bytes)
        current_step = progress_data["step"]

        # No new progress
        if current_step <= last_step:
            return None, last_step, False

        # Check for completion or error
        is_complete = progress_data["progress"] >= 100 or progress_data["progress"] == -1
        return progress_data, current_step, is_complete

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error for task {task_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error processing progress for task {task_id}: {e}")
        raise


@bp.route("/stream-progress/<task_id>")
@bp.response(200, description="Server-Sent Events stream of progress updates")
@bp.alt_response(
    404,
    schema=ErrorSchema,
    description="Task not found",
    example={
        "status": 404,
        "code": "RESULTS_NOT_FOUND",
        "message": "Results not found",
        "details": {"url": "/api/stream-progress/invalid_task_id", "task_id": "invalid_task_id"},
    },
)
@bp.alt_response(
    500,
    schema=ErrorSchema,
    description="Redis connection error",
    example={
        "status": 500,
        "code": "FAILED_TO_RETRIEVE_RESULTS",
        "message": "Failed to retrieve results",
        "details": {"url": "/api/stream-progress/task_123", "exception": "Redis connection failed"},
    },
)
def stream_progress(task_id: str) -> tuple[Response, int] | Response:
    """Stream progress updates via Server-Sent Events.

    Returns a continuous stream of progress data for the specified task.
    Stream continues until task completes or encounters an error.

    Path Parameters:
        - `task_id`: Task identifier returned from `/api/statistics/players`

    Returns:
        Server-Sent Events stream with progress updates (200) or error response (404, 500)

    Example:
        `GET /api/stream-progress/task_1234_1234567890`

        Stream (200):

        {"step": 1, "message": "Fetching matches...", "progress": 25, "data": {...}}
        {"step": 2, "message": "Processing...", "progress": 50, "data": {...}}
        {"step": 3, "message": "Completed", "progress": 100, "data": {...}}

    """
    # Verify task exists before starting stream
    try:
        initial_progress = redis_client.get(f"progress:{task_id}")
        if initial_progress is None:
            return ApiError.create_response(
                404,
                error=Errors.RESULTS_NOT_FOUND,
                details={"url": request.path, "task_id": task_id},
            )
    except Exception as e:
        logger.error(f"Redis error checking task {task_id}: {e}")
        return ApiError.create_response(
            500,
            error=Errors.FAILED_TO_RETRIEVE_RESULTS,
            details={"url": request.path, "exception": str(e)},
        )

    return Response(
        stream_with_context(_generate_progress_stream(task_id)),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "Access-Control-Allow-Origin": "*"},
    )


@bp.route("/results/<task_id>")
@bp.response(200, StatisticsResultSchema)
@bp.alt_response(
    404,
    schema=ErrorSchema,
    description="Results not found",
    example={
        "status": 404,
        "code": "RESULTS_NOT_FOUND",
        "message": "Results not found",
        "details": {"url": "/api/results/task_123", "task_id": "task_123"},
    },
)
@bp.alt_response(
    500,
    schema=ErrorSchema,
    description="Failed to retrieve results",
    example={
        "status": 500,
        "code": "FAILED_TO_RETRIEVE_RESULTS",
        "message": "Failed to retrieve results",
        "details": {"url": "/api/results/task_123", "exception": "Redis connection failed"},
    },
)
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
        `GET /api/results/task_12345_1234567890`

        Response (200):
        {
            "results": [...],
            "successful": 5,
            "total": 5,
            "summary": {...}
        }

    """
    try:
        results_data = redis_client.get(f"results:{task_id}")
        if not results_data:
            return ApiError.create_response(
                404,
                error=Errors.RESULTS_NOT_FOUND,
                details={"url": request.path, "task_id": task_id},
            )

        results = json.loads(results_data)
        return jsonify(results), 200
    except Exception as e:
        logger.error(f"Error retrieving results for task {task_id}: {e}")
        return ApiError.create_response(
            500,
            error=Errors.FAILED_TO_RETRIEVE_RESULTS,
            details={"url": request.path, "exception": str(e)},
        )


@bp.route("/pro-players/sync", methods=["POST"])
@bp.response(200, SyncResponseSchema)
@bp.alt_response(
    503,
    schema=ErrorSchema,
    description="API connection failed",
    example={
        "status": 503,
        "code": "FAILED_TO_FETCH_PRO_PLAYERS",
        "message": "Failed to fetch pro players from API",
        "details": {"url": "/api/pro-players/sync", "exception": "Connection timeout"},
    },
)
@bp.alt_response(
    502,
    schema=ErrorSchema,
    description="Invalid API response",
    example={
        "status": 502,
        "code": "FAILED_TO_FETCH_PRO_PLAYERS",
        "message": "Failed to fetch pro players from API",
        "details": {"url": "/api/pro-players/sync", "exception": "Invalid JSON response"},
    },
)
@bp.alt_response(
    500,
    schema=ErrorSchema,
    description="Database operation failed",
    example={
        "status": 500,
        "code": "FAILED_TO_STORE_PRO_PLAYERS",
        "message": "Failed to store pro players to database",
        "details": {"url": "/api/pro-players/sync", "exception": "Database connection error"},
    },
)
def sync_pro_players() -> tuple[Response, int]:
    """Sync pro players from OpenDota API to local database.

    Fetches fresh pro player data from OpenDota API and updates the d2ba database.
    Intended to run infrequently (e.g., once daily during maintenance).

    Returns the number of players successfully synced.
    """
    # Fetch data from OpenDota API
    try:
        players_data = fetch_pro_players_from_api()
    except ConnectionError as e:
        return ApiError.create_response(
            503,
            error=Errors.FAILED_TO_FETCH_PRO_PLAYERS,
            details={"url": request.path, "exception": str(e)},
        )
    except ValueError as e:
        return ApiError.create_response(
            502,
            error=Errors.FAILED_TO_FETCH_PRO_PLAYERS,
            details={"url": request.path, "exception": str(e)},
        )

    if not players_data:
        return jsonify({"synced_count": 0, "message": "No pro players data available"}), 200

    # Store to database
    try:
        count = store_pro_players(players_data)
        return jsonify({"synced_count": count, "message": f"Stored {count} pro players"}), 200
    except Exception as e:
        return ApiError.create_response(
            500,
            error=Errors.FAILED_TO_STORE_PRO_PLAYERS,
            details={"url": request.path, "exception": str(e)},
        )


@bp.route("/teams/sync", methods=["POST"])
@bp.response(200, SyncResponseSchema)
@bp.alt_response(
    503,
    schema=ErrorSchema,
    description="API connection failed",
    example={
        "status": 503,
        "code": "FAILED_TO_FETCH_TEAMS",
        "message": "Failed to fetch teams from API",
        "details": {"url": "/api/teams/sync", "exception": "Connection timeout"},
    },
)
@bp.alt_response(
    502,
    schema=ErrorSchema,
    description="Invalid API response",
    example={
        "status": 502,
        "code": "FAILED_TO_FETCH_TEAMS",
        "message": "Failed to fetch teams from API",
        "details": {"url": "/api/teams/sync", "exception": "Invalid JSON response"},
    },
)
@bp.alt_response(
    500,
    schema=ErrorSchema,
    description="Database operation failed",
    example={
        "status": 500,
        "code": "FAILED_TO_STORE_TEAMS",
        "message": "Failed to store teams to database",
        "details": {"url": "/api/teams/sync", "exception": "Database connection error"},
    },
)
def sync_teams() -> tuple[Response, int]:
    """Sync teams from OpenDota API to local database.

    Fetches fresh team data from OpenDota API (paginated, 1000 entries per page)
    and updates the d2ba database. Intended to run infrequently (e.g., once daily).

    Returns the number of teams successfully synced.
    """
    # Fetch data from OpenDota API (handles pagination internally)
    try:
        teams_data = fetch_teams_from_api()
    except ConnectionError as e:
        return ApiError.create_response(
            503,
            error=Errors.FAILED_TO_FETCH_TEAMS,
            details={"url": request.path, "exception": str(e)},
        )
    except ValueError as e:
        return ApiError.create_response(
            502,
            error=Errors.FAILED_TO_FETCH_TEAMS,
            details={"url": request.path, "exception": str(e)},
        )

    if not teams_data:
        return jsonify({"synced_count": 0, "message": "No teams data available"}), 200

    # Store to database
    try:
        count = store_teams(teams_data)
        return jsonify({"synced_count": count, "message": f"Stored {count} teams"}), 200
    except Exception as e:
        return ApiError.create_response(
            500,
            error=Errors.FAILED_TO_STORE_TEAMS,
            details={"url": request.path, "exception": str(e)},
        )


@bp.route("/teams/search", methods=["GET"])
@bp.arguments(TeamSearchQuerySchema, location="query")
@bp.response(200, TeamSchema(many=True))
@bp.alt_response(400, schema=ErrorSchema, description="Invalid query parameters")
@bp.alt_response(503, schema=ErrorSchema, description="Database connection error")
def search_teams(args):
    """Search for teams by name or tag for autocomplete.

    Returns a list of matching teams ordered by relevance (starts-with matches first).
    """
    from backend.pro_players import get_d2ba_db

    search_query = args["q"]
    limit = args.get("limit", 10)

    try:
        db = get_d2ba_db()
        cursor = db.cursor()

        # Search teams by name or tag (case-insensitive)
        # WHERE uses "contains" pattern; ORDER BY prioritizes "starts with" matches
        cursor.execute(
            """
            SELECT team_id, name, tag, logo_url, rating
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
            }
            for row in cursor.fetchall()
        ]

        return jsonify(teams), 200

    except Exception as e:
        logger.error(f"Error searching teams: {e!s}")
        return ApiError.create_response(
            503,
            error=Errors.SEARCH_ERROR,
            details={"url": request.path, "exception": str(e)},
        )


if __name__ == "__main__":
    from backend import create_app

    app = create_app()
    app.run(debug=True)

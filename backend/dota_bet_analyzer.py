import json
import os
import time

from celery import Celery  # type: ignore[import-untyped]
from flask import Response, jsonify, request, stream_with_context
from flask_smorest import Blueprint

from backend import __version__
from backend.config import Config
from backend.head_to_head import get_head_to_head
from backend.helpers import Errors, api_error
from backend.heroes import fetch_heroes_from_api, list_heroes, store_heroes
from backend.logging_config import setup_logging
from backend.matches import get_matches
from backend.predictions import (
    SnapshotMissingError,
    create_prediction,
    delete_prediction,
    get_prediction,
    list_predictions,
    save_review,
    update_decision,
)
from backend.pro_players import fetch_pro_players_from_api, store_pro_players
from backend.schemas import (
    ErrorSchema,
    HeadToHeadSchema,
    HeroSchema,
    MatchesSchema,
    PlayerStatisticsQuerySchema,
    PredictionCreateSchema,
    PredictionDecisionSchema,
    PredictionDetailSchema,
    PredictionListQuerySchema,
    PredictionReviewSchema,
    PredictionSchema,
    SnapshotCreateSchema,
    SnapshotDetailSchema,
    SnapshotListQuerySchema,
    SnapshotSchema,
    StatisticsResultSchema,
    StatsResponseSchema,
    SyncResponseSchema,
    TaskResponseSchema,
    TeamSchema,
    TeamSearchQuerySchema,
    TeamsSyncResponseSchema,
    TeamsSyncStatusSchema,
    TeamStatisticsQuerySchema,
    VersionSchema,
)
from backend.snapshots import get_snapshot, list_snapshots, save_snapshot
from backend.stats import (
    BAD_RANK_THRESHOLD,
    RankTally,
    compute_statistics,
    get_team_matches_summary,
)
from backend.task_store import (
    ProgressReporter,
    get_matches_cached,
    get_rank_cached,
    load_results,
    progress_exists,
    read_progress,
    store_results,
    subscribe_progress,
    update_progress,
    wait_for_progress,
)
from backend.teams_sync import (
    TeamsSyncRunningError,
    get_teams_synced_at,
    is_teams_sync_running,
    run_teams_sync,
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


@celery.task(bind=True)
def players_statistics_task(self, task_id, accounts: list[int], days: int = 20, rank_accounts: list[int] | None = None):
    """Celery task to fetch match statistics for multiple players.

    Saves one payload under `results:{task_id}` (read by GET /api/results/{task_id}, StatisticsResultSchema):
    - `summary`: team totals from get_team_matches_summary plus rank values; the only part the
      Team Comparison table reads (frontend getSummaryForTeam and the rows marked `summary: true`)
    - `results`: one entry per account with its match count and leaderboard rank, or its error
      (raw matches are not stored; the Team Insights table shows each player's rank from here).
      Accounts in `rank_accounts` get only `rank` (or `error`): they are not in `summary` or `successful`
    - `successful` / `total`: how many accounts were fetched; also sent in the final progress message

    Args:
        task_id: Unique task identifier for progress tracking
        accounts: List of account IDs to fetch statistics for
        days: Number of days of match history to fetch
        rank_accounts: Account IDs to fetch only the leaderboard rank for (stand-ins, no matches)
    """
    rank_accounts = rank_accounts or []
    progress = ProgressReporter(task_id, 2 + 2 * len(accounts) + len(rank_accounts))  # Initial + per-account + final
    try:
        logger.info(f"Starting players_statistics_task: task_id={task_id}, accounts={accounts}, days={days}")
        progress.start(f"Initializing match history fetch for {len(accounts)} players")

        results: list[dict[str, int | str | None]] = []  # Per player: match_count and rank, or the fetch error
        matches_stats = []  # List of lists: each inner list is matches for one player
        ranks = RankTally()
        for account_id in accounts:
            progress.next()

            def report_wait(delay: int, account_id: int = account_id) -> None:
                progress.waiting(delay, account_id)

            try:
                # Fetch match data for this account
                player_matches = get_matches_cached(account_id=account_id, days=days, on_wait=report_wait)
                matches_stats.append(player_matches)  # Append as a list per player

                # Only the count and rank are kept per player; the matches themselves feed `summary`
                result: dict[str, int | str | None] = {"account_id": account_id, "match_count": len(player_matches)}
                results.append(result)
                progress.report(
                    f"Fetched {len(player_matches)} matches for account {account_id}",
                    {"account_id": account_id, "match_count": len(player_matches)},
                )

                player_rank = get_rank_cached(account_id, on_wait=report_wait)
                result["rank"] = player_rank
                ranks.add(player_rank)
                if player_rank is not None and player_rank > BAD_RANK_THRESHOLD:  # Tysyachniks ruin the games.
                    logger.info(f"Account {account_id} is tysyachnik and will ruin the games for high rank players")
                progress.report(
                    f"Got Player rank {player_rank} for account {account_id}",
                    {"account_id": account_id, "player_rank": player_rank},
                )

            except Exception as e:
                # Handle per-account errors gracefully
                # The player is left out of `summary`; the error stays visible in the results payload
                results.append({"account_id": account_id, "error": str(e)})
                progress.report(
                    f"Error fetching data for account {account_id}: {e!s}",
                    {"account_id": account_id, "error": str(e)},
                )

            time.sleep(0.01)  # Short sleep to prevent overwhelming the API

        summary = get_team_matches_summary(matches_stats)  # This is heavy logic. To check.
        summary.avg_rank = ranks.average
        summary.bad_rank_players = ranks.bad_rank_players

        successful = len([r for r in results if "error" not in r])

        for account_id in rank_accounts:
            progress.next()

            def report_wait(delay: int, account_id: int = account_id) -> None:
                progress.waiting(delay, account_id)

            try:
                player_rank = get_rank_cached(account_id, on_wait=report_wait)
                results.append({"account_id": account_id, "rank": player_rank})
                progress.report(
                    f"Got Player rank {player_rank} for account {account_id}",
                    {"account_id": account_id, "player_rank": player_rank},
                )
            except Exception as e:
                results.append({"account_id": account_id, "error": str(e)})
                progress.report(
                    f"Error fetching rank for account {account_id}: {e!s}",
                    {"account_id": account_id, "error": str(e)},
                )

            time.sleep(0.01)

        # Store heavy results separately (not in progress stream)
        store_results(
            task_id,
            {
                "results": results,
                "successful": successful,
                "total": len(accounts),
                "summary": summary.model_dump(),
            },
        )

        # Lightweight final message (no heavy data)
        progress.done(
            f"Completed: fetched data for {successful}/{len(accounts)} players",
            {"successful": successful, "total": len(accounts)},
        )

    except Exception as exc:
        logger.error(f"Task error for task_id={task_id}: {exc}", exc_info=True)
        progress.fail(exc)
        raise


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
                "backend": _full_version(),
                "build": _build_number(),
            }
        ),
        200,
    )


def _build_number() -> str:
    """Build number of the running backend (DEV when not set)."""
    return os.environ.get("BUILD_NUMBER", "DEV")


def _full_version() -> str:
    """Backend version with build number, as shown by /api/version."""
    return f"{__version__}.{_build_number()}"


@bp.route("/statistics", methods=["GET"])
@bp.arguments(TeamStatisticsQuerySchema, location="query")
@bp.response(200, StatsResponseSchema)
@bp.alt_response(
    400,
    schema=ErrorSchema,
    description="Invalid request",
    example={
        "status": 400,
        "code": "INVALID_REQUEST",
        "message": "Invalid request",
        "details": {"url": "/api/statistics", "exception": "Invalid team data"},
    },
)
@bp.alt_response(
    422,
    schema=ErrorSchema,
    description="Validation failed - missing teams, too many teams (>10), or invalid parameter format",
    example={
        "status": 422,
        "code": "MISSING_TEAMS",
        "message": "No teams provided",
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
            task_id = f"task_{int(time.time())}"
            # Queue before the task starts, so a finished task's progress is never overwritten
            update_progress(task_id, 0, "Queued", 0)
            task = players_statistics_task.delay(task_id=task_id, accounts=accounts_int, days=days)
            return jsonify({"status": "started", "task_id": task_id, "celery_task_id": task.id}), 200
        except Exception as e:
            return api_error(500, Errors.FAILED_TO_START_TASK, e, task_id=task_id)

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

    Returns a continuous stream of progress data for the specified task, one JSON object
    per line, sent as soon as the task's progress changes. The stream ends when the task
    completes (100) or fails (-1), or with a timeout line after 30s without changes or 120s
    in total; clients reopen it until the task completes.

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
        results = load_results(task_id)
        if results is None:
            return api_error(404, Errors.RESULTS_NOT_FOUND, task_id=task_id)

        return jsonify(results), 200
    except Exception as e:
        logger.error(f"Error retrieving results for task {task_id}: {e}")
        return api_error(500, Errors.FAILED_TO_RETRIEVE_RESULTS, e)


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
        return api_error(503, Errors.FAILED_TO_FETCH_PRO_PLAYERS, e)
    except ValueError as e:
        return api_error(502, Errors.FAILED_TO_FETCH_PRO_PLAYERS, e)

    if not players_data:
        return jsonify({"synced_count": 0, "message": "No pro players data available"}), 200

    # Store to database
    try:
        count = store_pro_players(players_data)
        return jsonify({"synced_count": count, "message": f"Stored {count} pro players"}), 200
    except Exception as e:
        return api_error(500, Errors.FAILED_TO_STORE_PRO_PLAYERS, e)


@bp.route("/teams/sync", methods=["GET"])
@bp.response(200, TeamsSyncStatusSchema)
@bp.alt_response(500, schema=ErrorSchema, description="Database read failed")
def get_teams_sync_status() -> tuple[Response, int]:
    """When the teams list was last synced, and whether a sync is running now (no OpenDota request)."""
    try:
        synced_at = get_teams_synced_at()
    except Exception as e:
        return api_error(500, Errors.FAILED_TO_READ_SYNC_STATE, e)
    return jsonify({"synced_at": synced_at, "running": is_teams_sync_running()}), 200


@bp.route("/teams/sync", methods=["POST"])
@bp.response(200, TeamsSyncResponseSchema)
@bp.alt_response(
    409,
    schema=ErrorSchema,
    description="A teams sync is already running (started from the UI or at startup)",
    example={
        "status": 409,
        "code": "TEAMS_SYNC_RUNNING",
        "message": "Teams sync is already running",
        "details": {"url": "/api/teams/sync"},
    },
)
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

    Fetches fresh team data from OpenDota API (paginated, 1000 entries per page) and updates the d2ba database.
    Also runs at startup when the last sync is 30+ days old. Only one sync runs at a time.

    Returns the number of teams successfully synced and the time of the last successful sync.
    """
    try:
        count = run_teams_sync()
    except TeamsSyncRunningError:
        return api_error(409, Errors.TEAMS_SYNC_RUNNING)
    except ConnectionError as e:
        return api_error(503, Errors.FAILED_TO_FETCH_TEAMS, e)
    except ValueError as e:
        return api_error(502, Errors.FAILED_TO_FETCH_TEAMS, e)
    except Exception as e:
        return api_error(500, Errors.FAILED_TO_STORE_TEAMS, e)

    message = f"Stored {count} teams" if count else "No teams data available"
    return jsonify({"synced_count": count, "message": message, "synced_at": get_teams_synced_at()}), 200


@bp.route("/heroes", methods=["GET"])
@bp.response(200, HeroSchema(many=True))
@bp.alt_response(500, schema=ErrorSchema, description="Database operation failed")
def get_heroes() -> tuple[Response, int]:
    """List the cached heroes (id, names, icon URL) ordered by display name.

    Reads d2ba.sqlite only, no OpenDota request. The list is filled at startup when empty, or by POST /heroes/sync.
    """
    try:
        return jsonify(list_heroes()), 200
    except Exception as e:
        return api_error(500, Errors.FAILED_TO_READ_HEROES, e)


@bp.route("/heroes/sync", methods=["POST"])
@bp.response(200, SyncResponseSchema)
@bp.alt_response(503, schema=ErrorSchema, description="API connection failed")
@bp.alt_response(502, schema=ErrorSchema, description="Invalid API response")
@bp.alt_response(500, schema=ErrorSchema, description="Database operation failed")
def sync_heroes() -> tuple[Response, int]:
    """Refresh the hero list from OpenDota /constants/heroes (one request).

    Returns the number of heroes stored.
    """
    try:
        heroes = fetch_heroes_from_api()
    except ConnectionError as e:
        return api_error(503, Errors.FAILED_TO_FETCH_HEROES, e)
    except ValueError as e:
        return api_error(502, Errors.FAILED_TO_FETCH_HEROES, e)

    try:
        count = store_heroes(heroes)
        return jsonify({"synced_count": count, "message": f"Stored {count} heroes"}), 200
    except Exception as e:
        return api_error(500, Errors.FAILED_TO_STORE_HEROES, e)


@bp.route("/matches", methods=["GET"])
@bp.response(200, MatchesSchema)
@bp.alt_response(503, schema=ErrorSchema, description="Liquipedia could not be reached or its page could not be read")
@bp.alt_response(500, schema=ErrorSchema, description="Database error")
def list_matches() -> tuple[Response, int]:
    """Upcoming (soonest first) and recently finished (newest first) pro series from Liquipedia.

    One Liquipedia request at most every 10 minutes (cached in Redis); no OpenDota request. Teams are matched by
    name to the teams table for their OpenDota ID and logo.
    """
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


@bp.route("/snapshots", methods=["POST"])
@bp.arguments(SnapshotCreateSchema)
@bp.response(201, SnapshotSchema, description="New snapshot saved")
@bp.alt_response(200, schema=SnapshotSchema, description="Snapshot with the same key refreshed")
@bp.alt_response(422, schema=ErrorSchema, description="Invalid body, or team_id differs from team.team_id")
@bp.alt_response(500, schema=ErrorSchema, description="Database error")
def create_snapshot(args) -> tuple[Response, int]:
    """Save what the Compare page shows for one team.

    A snapshot is identified by team + UTC day + `days` + the team's latest league match (`team.latest_match_time`).
    Saving the same key again refreshes the stored data and returns 200; a new key returns 201. No OpenDota requests.
    """
    team_id = args["team_id"]
    if args["team"].get("team_id") not in (None, team_id):
        return api_error(422, Errors.TEAM_ID_MISMATCH, team_id=team_id, team_team_id=args["team"].get("team_id"))
    try:
        snapshot, created = save_snapshot(
            team_id, args["days"], args["team"], args["summary"], args["players"], _full_version()
        )
        return jsonify(snapshot), 201 if created else 200
    except Exception as e:
        logger.error(f"Error storing snapshot for team {team_id}: {e}")
        return api_error(500, Errors.FAILED_TO_STORE_SNAPSHOT, e)


@bp.route("/snapshots", methods=["GET"])
@bp.arguments(SnapshotListQuerySchema, location="query")
@bp.response(200, SnapshotSchema(many=True))
@bp.alt_response(422, schema=ErrorSchema, description="Invalid query parameters")
@bp.alt_response(500, schema=ErrorSchema, description="Database error")
def get_snapshots(args) -> tuple[Response, int]:
    """List saved team snapshots without their data, newest first.

    Filter by `team_id` and by UTC day with `from` and `to` (YYYY-MM-DD, inclusive).
    """
    try:
        snapshots = list_snapshots(args.get("team_id"), args.get("date_from"), args.get("date_to"))
        return jsonify(snapshots), 200
    except Exception as e:
        logger.error(f"Error listing snapshots: {e}")
        return api_error(500, Errors.FAILED_TO_READ_SNAPSHOTS, e)


@bp.route("/snapshots/<int:snapshot_id>", methods=["GET"])
@bp.response(200, SnapshotDetailSchema)
@bp.alt_response(404, schema=ErrorSchema, description="Snapshot not found")
@bp.alt_response(500, schema=ErrorSchema, description="Database error")
def get_snapshot_by_id(snapshot_id: int) -> tuple[Response, int]:
    """Get one saved team snapshot with its data (`team`, `summary`, `players`)."""
    try:
        snapshot = get_snapshot(snapshot_id)
    except Exception as e:
        logger.error(f"Error reading snapshot {snapshot_id}: {e}")
        return api_error(500, Errors.FAILED_TO_READ_SNAPSHOTS, e)
    if snapshot is None:
        return api_error(404, Errors.SNAPSHOT_NOT_FOUND, snapshot_id=snapshot_id)
    return jsonify(snapshot), 200


@bp.route("/predictions", methods=["POST"])
@bp.arguments(PredictionCreateSchema)
@bp.response(201, PredictionSchema, description="Prediction saved")
@bp.alt_response(404, schema=ErrorSchema, description="Snapshot not found")
@bp.alt_response(422, schema=ErrorSchema, description="Invalid body")
@bp.alt_response(500, schema=ErrorSchema, description="Database error")
def post_prediction(args) -> tuple[Response, int]:
    """Save a series-win prediction made from two saved team snapshots.

    Both snapshots are locked from then on (saving their key again no longer refreshes them). Odds, `best_of`, bet
    and comment can be edited later with PUT. No OpenDota requests.
    """
    try:
        prediction = create_prediction(**args)
    except SnapshotMissingError as e:
        return api_error(404, Errors.SNAPSHOT_NOT_FOUND, snapshot_id=e.snapshot_id)
    except Exception as e:
        logger.error(f"Error storing prediction: {e}")
        return api_error(500, Errors.FAILED_TO_STORE_PREDICTION, e)
    return jsonify(prediction), 201


@bp.route("/predictions", methods=["GET"])
@bp.arguments(PredictionListQuerySchema, location="query")
@bp.response(200, PredictionSchema(many=True))
@bp.alt_response(422, schema=ErrorSchema, description="Invalid query parameters")
@bp.alt_response(500, schema=ErrorSchema, description="Database error")
def get_predictions(args) -> tuple[Response, int]:
    """List predictions, newest first, with team names and logos from their snapshots and computed `bet_won`.

    `status=pending` lists those without a result, `status=settled` those with one.
    """
    try:
        return jsonify(list_predictions(args.get("status"))), 200
    except Exception as e:
        logger.error(f"Error listing predictions: {e}")
        return api_error(500, Errors.FAILED_TO_READ_PREDICTIONS, e)


@bp.route("/predictions/<int:prediction_id>", methods=["GET"])
@bp.response(200, PredictionDetailSchema)
@bp.alt_response(404, schema=ErrorSchema, description="Prediction not found")
@bp.alt_response(500, schema=ErrorSchema, description="Database error")
def get_prediction_by_id(prediction_id: int) -> tuple[Response, int]:
    """Get one prediction with both snapshots and their data, for the review page."""
    try:
        prediction = get_prediction(prediction_id)
    except Exception as e:
        logger.error(f"Error reading prediction {prediction_id}: {e}")
        return api_error(500, Errors.FAILED_TO_READ_PREDICTIONS, e)
    if prediction is None:
        return api_error(404, Errors.PREDICTION_NOT_FOUND, prediction_id=prediction_id)
    return jsonify(prediction), 200


@bp.route("/predictions/<int:prediction_id>/head-to-head", methods=["GET"])
@bp.response(200, HeadToHeadSchema)
@bp.alt_response(404, schema=ErrorSchema, description="Prediction not found")
@bp.alt_response(500, schema=ErrorSchema, description="Database error")
def get_prediction_head_to_head(prediction_id: int) -> tuple[Response, int]:
    """League matches between the prediction's two teams, from `days` before the prediction up to now.

    Read from team 1's cached team matches: no OpenDota request while the cache is fresh, otherwise one.
    """
    try:
        head_to_head = get_head_to_head(prediction_id)
    except Exception as e:
        logger.error(f"Error reading head-to-head of prediction {prediction_id}: {e}")
        return api_error(500, Errors.FAILED_TO_READ_PREDICTIONS, e)
    if head_to_head is None:
        return api_error(404, Errors.PREDICTION_NOT_FOUND, prediction_id=prediction_id)
    return jsonify(head_to_head), 200


@bp.route("/predictions/<int:prediction_id>", methods=["PATCH"])
@bp.arguments(PredictionReviewSchema)
@bp.response(200, PredictionSchema, description="Review saved")
@bp.alt_response(404, schema=ErrorSchema, description="Prediction not found")
@bp.alt_response(422, schema=ErrorSchema, description="Invalid body, or the score does not fit best_of")
@bp.alt_response(500, schema=ErrorSchema, description="Database error")
def patch_prediction(args, prediction_id: int) -> tuple[Response, int]:
    """Save the review: the actual result as maps won by each team, and a review note.

    The score must be a finished series of the prediction's format (bo3: 2-0, 2-1, 1-2, 0-2, bo2: 2-0, 1-1, 0-2).
    With an unknown format any score with at least one map is accepted.
    Other fields (odds, bet, comment) are rejected, they are edited with PUT.
    """
    try:
        prediction = save_review(prediction_id, args["team1_maps_won"], args["team2_maps_won"], args.get("review_note"))
    except ValueError as e:
        return api_error(
            422,
            Errors.INVALID_RESULT,
            team1_maps_won=args["team1_maps_won"],
            team2_maps_won=args["team2_maps_won"],
            reason=str(e),
        )
    except Exception as e:
        logger.error(f"Error saving review of prediction {prediction_id}: {e}")
        return api_error(500, Errors.FAILED_TO_STORE_PREDICTION, e)
    if prediction is None:
        return api_error(404, Errors.PREDICTION_NOT_FOUND, prediction_id=prediction_id)
    return jsonify(prediction), 200


@bp.route("/predictions/<int:prediction_id>", methods=["PUT"])
@bp.arguments(PredictionDecisionSchema)
@bp.response(200, PredictionSchema, description="Prediction updated")
@bp.alt_response(404, schema=ErrorSchema, description="Prediction not found")
@bp.alt_response(422, schema=ErrorSchema, description="Invalid body, or the saved result does not fit the new best_of")
@bp.alt_response(500, schema=ErrorSchema, description="Database error")
def put_prediction(args, prediction_id: int) -> tuple[Response, int]:
    """Edit a saved prediction: odds, `best_of`, bet, stake and comment, all replaced together.

    The snapshots and the review stay. When a result is saved, the new `best_of` must still fit it.
    """
    try:
        prediction = update_decision(prediction_id, **args)
    except ValueError as e:
        return api_error(422, Errors.INVALID_RESULT, best_of=args["best_of"], reason=str(e))
    except Exception as e:
        logger.error(f"Error editing prediction {prediction_id}: {e}")
        return api_error(500, Errors.FAILED_TO_STORE_PREDICTION, e)
    if prediction is None:
        return api_error(404, Errors.PREDICTION_NOT_FOUND, prediction_id=prediction_id)
    return jsonify(prediction), 200


@bp.route("/predictions/<int:prediction_id>", methods=["DELETE"])
@bp.response(204, description="Prediction deleted, its snapshots stay")
@bp.alt_response(404, schema=ErrorSchema, description="Prediction not found")
@bp.alt_response(500, schema=ErrorSchema, description="Database error")
def remove_prediction(prediction_id: int) -> tuple[Response, int] | tuple[str, int]:
    """Delete a prediction made by mistake. Its snapshots stay (and stay locked if another prediction uses them)."""
    try:
        deleted = delete_prediction(prediction_id)
    except Exception as e:
        logger.error(f"Error deleting prediction {prediction_id}: {e}")
        return api_error(500, Errors.FAILED_TO_STORE_PREDICTION, e)
    if not deleted:
        return api_error(404, Errors.PREDICTION_NOT_FOUND, prediction_id=prediction_id)
    return "", 204


if __name__ == "__main__":
    from backend import create_app

    app = create_app()
    app.run(debug=True)

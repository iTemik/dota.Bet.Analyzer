import json
import os
import time

import redis
from celery import Celery  # type: ignore[import-untyped]
from flask import Response, jsonify, request, stream_with_context
from flask_smorest import Blueprint

from backend import __version__
from backend.config import Config
from backend.helpers import Errors, error_response
from backend.logging_config import setup_logging
from backend.pro_players import (
    fetch_pro_players_from_api,
    fetch_teams_from_api,
    store_pro_players,
    store_teams,
)
from backend.schemas import (
    PlayerStatisticsErrorSchema,
    PlayerStatisticsQuerySchema,
    StatisticsErrorSchema,
    StatisticsResultSchema,
    StatsResponseSchema,
    SyncErrorSchema,
    SyncResponseSchema,
    TaskResponseSchema,
    TaskResultsErrorSchema,
    TeamSchema,
    TeamSearchErrorSchema,
    TeamSearchQuerySchema,
    VersionSchema,
)
from backend.stats import (
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
@bp.response(200, StatsResponseSchema)
@bp.alt_response(400, schema=StatisticsErrorSchema, description="Invalid parameters")
@bp.alt_response(500, schema=StatisticsErrorSchema, description="Computation failed")
def statistics() -> tuple[Response, int]:
    """Compute team statistics.

    Query parameters:
    - team: Team name (supports multiple values: ?team=Alpha&team=Beta)
    - team1, team2, ...: Alternative numbered format (legacy support)

    Returns computed statistics for the specified teams (1-10 teams).
    Includes team ratings, tags, IDs, rating deltas, player lists, and task_id
    for asynchronous player statistics computation.
    """
    teams = request.args.getlist("team")
    if not teams:
        teams = [v for k, v in sorted(request.args.items()) if k.startswith("team")]

    # Normalize & validate
    teams = [t.strip() for t in teams if isinstance(t, str) and t.strip()]
    if not teams:
        return jsonify(error_response(Errors.MISSING_TEAMS, status_code=400)), 400
    if len(teams) > 10:
        return jsonify(error_response(Errors.TOO_MANY_TEAMS, status_code=400, limit=10)), 400

    stats = compute_statistics(teams)
    return jsonify(stats.model_dump()), 200


@bp.route("/statistics/players", methods=["GET"])
@bp.arguments(PlayerStatisticsQuerySchema, location="query")
@bp.response(200, TaskResponseSchema)
@bp.alt_response(400, schema=PlayerStatisticsErrorSchema, description="Invalid parameters")
@bp.alt_response(500, schema=PlayerStatisticsErrorSchema, description="Task start failed")
def players_statistics(args) -> tuple[Response, int]:
    """Start player statistics computation task.

    Initiates an asynchronous task to compute statistics for specified players.
    Returns a task_id for tracking progress via /stream-progress endpoint.
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
            return (
                jsonify(
                    {
                        "status": 500,
                        "code": Errors.FAILED_TO_START_TASK.code,
                        "message": Errors.FAILED_TO_START_TASK.message,
                        "details": {"task_id": task_id, "url": request.path, "exception": f"{e!s}"},
                    }
                ),
                500,
            )

    except Exception as e:
        return (
            jsonify(
                {
                    "status": 400,
                    "code": Errors.INVALID_REQUEST.code,
                    "message": Errors.INVALID_REQUEST.message,
                    "details": {"url": request.path, "exception": f"{e!s}"},
                }
            ),
            400,
        )


@bp.route("/stream-progress/<task_id>")
@bp.response(200, description="Server-Sent Events stream of progress updates")
def stream_progress(task_id: str) -> Response:
    """Stream progress updates via Server-Sent Events.

    Returns a continuous stream of progress data for the specified task.
    Stream continues until task completes or encounters an error.
    """

    def generate():
        """Yield progress updates for a task.

        Reads lightweight progress snapshots from Redis and emits them
        until the task reaches completion or an error state.
        """
        last_step = 0

        while True:
            # Get progress from Redis
            progress_data = redis_client.get(f"progress:{task_id}")

            if progress_data:
                current_data = json.loads(progress_data)
                current_step = current_data["step"]

                # Send update if there's new progress
                if current_step > last_step:
                    yield f"{json.dumps(current_data)}\n"
                    last_step = current_step

                    # Break if complete or error
                    if current_data["progress"] >= 100 or current_data["progress"] == -1:
                        break

            time.sleep(0.01)  # Short sleep for tests

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "Access-Control-Allow-Origin": "*"},
    )


@bp.route("/results/<task_id>")
@bp.response(200, StatisticsResultSchema)
@bp.alt_response(404, schema=TaskResultsErrorSchema, description="Results not found")
@bp.alt_response(500, schema=TaskResultsErrorSchema, description="Failed to retrieve results")
def get_results(task_id: str) -> tuple[Response, int]:
    """Retrieve final computation results for a completed task.

    Returns detailed results including all analyzed matches and summary statistics.
    Returns 404 if results not found or task is still in progress.
    """
    try:
        results_data = redis_client.get(f"results:{task_id}")
        if not results_data:
            return (
                jsonify(
                    {
                        "status": 404,
                        "code": Errors.RESULTS_NOT_FOUND.code,
                        "message": Errors.RESULTS_NOT_FOUND.message,
                        "details": {"url": request.path, "task_id": task_id},
                    }
                ),
                404,
            )

        results = json.loads(results_data)
        return jsonify(results), 200
    except Exception as e:
        logger.error(f"Error retrieving results for task {task_id}: {e}")
        return (
            jsonify(
                {
                    "status": 500,
                    "code": Errors.FAILED_TO_RETRIEVE_RESULTS.code,
                    "message": Errors.FAILED_TO_RETRIEVE_RESULTS.message,
                    "details": {"url": request.path, "exception": f"{e!s}"},
                }
            ),
            500,
        )


@bp.route("/pro-players/sync", methods=["POST"])
@bp.response(200, SyncResponseSchema)
@bp.alt_response(503, schema=SyncErrorSchema, description="API connection failed")
@bp.alt_response(500, schema=SyncErrorSchema, description="Database operation failed")
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
        return (
            jsonify(
                {
                    "status": 503,
                    "code": Errors.FAILED_TO_FETCH_PRO_PLAYERS.code,
                    "message": Errors.FAILED_TO_FETCH_PRO_PLAYERS.message,
                    "details": {"url": request.path, "exception": f"{e!s}"},
                }
            ),
            503,
        )
    except ValueError as e:
        return (
            jsonify(
                {
                    "status": 502,
                    "code": Errors.FAILED_TO_FETCH_PRO_PLAYERS.code,
                    "message": Errors.FAILED_TO_FETCH_PRO_PLAYERS.message,
                    "details": {"url": request.path, "exception": f"{e!s}"},
                }
            ),
            502,
        )

    if not players_data:
        return jsonify({"synced_count": 0, "message": "No pro players data available"}), 200

    # Store to database
    try:
        count = store_pro_players(players_data)
        return jsonify({"synced_count": count, "message": f"Stored {count} pro players"}), 200
    except Exception as e:
        return (
            jsonify(
                {
                    "status": 500,
                    "code": Errors.FAILED_TO_STORE_PRO_PLAYERS.code,
                    "message": Errors.FAILED_TO_STORE_PRO_PLAYERS.message,
                    "details": {"url": request.path, "exception": f"{e!s}"},
                }
            ),
            500,
        )


@bp.route("/teams/sync", methods=["POST"])
@bp.response(200, SyncResponseSchema)
@bp.alt_response(503, schema=SyncErrorSchema, description="API connection failed")
@bp.alt_response(500, schema=SyncErrorSchema, description="Database operation failed")
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
        return (
            jsonify(
                {
                    "status": 503,
                    "code": Errors.FAILED_TO_FETCH_TEAMS.code,
                    "message": Errors.FAILED_TO_FETCH_TEAMS.message,
                    "details": {"url": request.path, "exception": f"{e!s}"},
                }
            ),
            503,
        )
    except ValueError as e:
        return (
            jsonify(
                {
                    "status": 502,
                    "code": Errors.FAILED_TO_FETCH_TEAMS.code,
                    "message": Errors.FAILED_TO_FETCH_TEAMS.message,
                    "details": {"url": request.path, "exception": f"{e!s}"},
                }
            ),
            502,
        )

    if not teams_data:
        return jsonify({"synced_count": 0, "message": "No teams data available"}), 200

    # Store to database
    try:
        count = store_teams(teams_data)
        return jsonify({"synced_count": count, "message": f"Stored {count} teams"}), 200
    except Exception as e:
        return (
            jsonify(
                {
                    "status": 500,
                    "code": Errors.FAILED_TO_STORE_TEAMS.code,
                    "message": Errors.FAILED_TO_STORE_TEAMS.message,
                    "details": {"url": request.path, "exception": f"{e!s}"},
                }
            ),
            500,
        )


@bp.route("/teams/search", methods=["GET"])
@bp.arguments(TeamSearchQuerySchema, location="query")
@bp.response(200, TeamSchema(many=True))
@bp.alt_response(400, schema=TeamSearchErrorSchema, description="Invalid query parameters")
@bp.alt_response(503, schema=TeamSearchErrorSchema, description="Database connection error")
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
        return (
            jsonify(
                {
                    "status": 503,
                    "code": Errors.SEARCH_ERROR.code,
                    "message": Errors.SEARCH_ERROR.message,
                    "details": {"url": request.path, "exception": f"{e!s}"},
                }
            ),
            503,
        )


if __name__ == "__main__":
    from backend import create_app

    app = create_app()
    app.run(debug=True)

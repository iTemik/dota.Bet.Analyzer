import json
import os
import time

import redis
from celery import Celery  # type: ignore[import-untyped]
from flask import Blueprint, Response, jsonify, request, stream_with_context

from backend import __version__
from backend.config import Config
from backend.helpers import ErrorCode
from backend.logging_config import setup_logging
from backend.pro_players import (
    fetch_pro_players_from_api,
    fetch_teams_from_api,
    store_pro_players,
    store_teams,
)
from backend.stats import (
    compute_statistics,
    get_matches,
    get_rank,
    get_team_matches_summary,
)

# Setup logger
logger = setup_logging(__name__)


bp = Blueprint("dota", __name__)

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
def get_version() -> tuple[Response, int]:
    """Get backend and frontend versions.

    Returns:
        Tuple of (JSON response, HTTP status code)
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


@bp.route("/statistics/players", methods=["GET"])
def players_statistics() -> tuple[Response, int]:
    """Start calculation and return task ID"""
    try:
        if request.method == "GET":
            accounts = request.args.getlist("account_id")
            days: int = int(request.args.get("days", 20))

        if not accounts:
            return (
                jsonify(
                    {
                        "error_code": ErrorCode.MISSING_ACCOUNT_IDS,
                        "message": "no account_ids provided",
                        "details": {"url": request.path},
                    }
                ),
                400,
            )
        if len(accounts) > 10:
            return (
                jsonify(
                    {
                        "error_code": ErrorCode.TOO_MANY_PLAYERS,
                        "message": "too many players (account_ids) in the team (max 10)",
                        "details": {"url": request.path, "limit": 10},
                    }
                ),
                400,
            )

        # Convert accounts to integers and filter valid ones
        accounts_int = []
        for a in accounts:
            if isinstance(a, str):
                a = a.strip()
                try:
                    accounts_int.append(int(a))
                except ValueError:
                    return (
                        jsonify(
                            {
                                "error_code": ErrorCode.INVALID_ACCOUNT_ID,
                                "message": f"Invalid account_id: {a}",
                                "details": {"url": request.path, "value": a},
                            }
                        ),
                        400,
                    )

        if not accounts_int:
            return (
                jsonify(
                    {
                        "error_code": ErrorCode.MISSING_ACCOUNT_IDS,
                        "message": "no valid account_ids provided",
                        "details": {"url": request.path},
                    }
                ),
                400,
            )

        try:
            task = players_statistics_task.delay(
                task_id := f"task_{int(time.time())}", accounts=accounts_int, days=days
            )
            return jsonify({"status": "started", "task_id": task_id, "celery_task_id": task.id}), 200
        except Exception as e:
            return (
                jsonify(
                    {
                        "error_code": ErrorCode.FAILED_TO_START_TASK,
                        "message": f"Failed to start task: {e!s}",
                        "details": {"url": request.path},
                    }
                ),
                500,
            )

    except Exception as e:
        return (
            jsonify(
                {
                    "error_code": ErrorCode.INVALID_REQUEST,
                    "message": f"Invalid request: {e!s}",
                    "details": {"url": request.path},
                }
            ),
            400,
        )


@bp.route("/stream-progress/<task_id>")
def stream_progress(task_id: str) -> Response:
    """Stream progress updates (lightweight data only)"""

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
def get_results(task_id: str) -> tuple[Response, int]:
    """Retrieve final computation results for a completed task.

    Returns:
        JSON response with detailed results including all matches and summary statistics.
        Returns 404 if results not found or task still in progress.
    """
    try:
        results_data = redis_client.get(f"results:{task_id}")
        if not results_data:
            return (
                jsonify(
                    {
                        "error_code": ErrorCode.RESULTS_NOT_FOUND,
                        "message": "Results not found. Task may still be in progress.",
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
                    "error_code": ErrorCode.FAILED_TO_RETRIEVE_RESULTS,
                    "message": f"Failed to retrieve results: {e}",
                    "details": {"url": request.path},
                }
            ),
            500,
        )


@bp.route("/statistics", methods=["GET", "POST"])
def statistics() -> tuple[Response, int]:
    """Get statistics for teams provided by arguments.

    Supports:
      - GET /statistics?team=aaa&team=bbb
      - POST /statistics with JSON body: {"teams": ["aaa", "bbb"]}
    """
    teams = []

    if request.method == "GET":
        teams = request.args.getlist("team")
        if not teams:
            teams = [v for k, v in sorted(request.args.items()) if k.startswith("team")]
    elif request.method == "POST":
        body = request.get_json(silent=True)
        if not body or "teams" not in body:
            return (
                jsonify(
                    {
                        "error_code": ErrorCode.MISSING_TEAMS,
                        "message": "no teams provided",
                        "details": {"url": request.path},
                    }
                ),
                400,
            )
        teams = body.get("teams") or []
    else:
        return (
            jsonify(
                {
                    "error_code": ErrorCode.UNSUPPORTED_METHOD,
                    "message": "unsupported method",
                    "details": {"url": request.path, "method": request.method},
                }
            ),
            400,
        )

    # Normalize & validate
    teams = [t.strip() for t in teams if isinstance(t, str) and t.strip()]
    if not teams:
        return (
            jsonify(
                {
                    "error_code": ErrorCode.MISSING_TEAMS,
                    "message": "no teams provided",
                    "details": {"url": request.path},
                }
            ),
            400,
        )
    if len(teams) > 10:
        return (
            jsonify(
                {
                    "error_code": ErrorCode.TOO_MANY_TEAMS,
                    "message": "too many teams (max 10)",
                    "details": {"url": request.path, "limit": 10},
                }
            ),
            400,
        )

    stats = compute_statistics(teams)
    return jsonify(stats.model_dump()), 200


@bp.route("/pro-players/sync", methods=["POST"])
def sync_pro_players() -> tuple[Response, int]:
    """Sync pro players from OpenDota API and update database.

    This is a write operation (POST) that fetches fresh pro player data from OpenDota API
    and updates the local database. It's intended to run infrequently (once daily during
    initialization/maintenance).

    Returns:
        JSON response with status and count of players stored.
    """
    # Fetch data from OpenDota API
    try:
        players_data = fetch_pro_players_from_api()
    except ConnectionError as e:
        return (
            jsonify(
                {
                    "error_code": ErrorCode.FAILED_TO_FETCH_PRO_PLAYERS,
                    "message": str(e),
                    "details": {"url": request.path},
                }
            ),
            503,
        )
    except ValueError as e:
        return (
            jsonify(
                {
                    "error_code": ErrorCode.FAILED_TO_FETCH_PRO_PLAYERS,
                    "message": f"Invalid response from OpenDota API: {e}",
                    "details": {"url": request.path},
                }
            ),
            502,
        )

    if not players_data:
        return jsonify({"count": 0, "message": "No pro players data available"}), 200

    # Store to database
    try:
        count = store_pro_players(players_data)
        return jsonify({"count": count, "message": f"Stored {count} pro players"}), 200
    except Exception as e:
        return (
            jsonify(
                {
                    "error_code": ErrorCode.FAILED_TO_STORE_PRO_PLAYERS,
                    "message": f"Failed to store pro players: {e!s}",
                    "details": {"url": request.path},
                }
            ),
            500,
        )


@bp.route("/teams/sync", methods=["POST"])
def sync_teams() -> tuple[Response, int]:
    """Sync teams from OpenDota API and update database.

    This is a write operation (POST) that fetches fresh team data from OpenDota API
    (paginated in 1000-entry pages) and updates the local database. It's intended to run
    infrequently (once daily during initialization/maintenance).

    Returns:
        JSON response with status and count of teams stored.
    """
    # Fetch data from OpenDota API (handles pagination internally)
    try:
        teams_data = fetch_teams_from_api()
    except ConnectionError as e:
        return (
            jsonify(
                {
                    "error_code": ErrorCode.FAILED_TO_FETCH_TEAMS,
                    "message": str(e),
                    "details": {"url": request.path},
                }
            ),
            503,
        )
    except ValueError as e:
        return (
            jsonify(
                {
                    "error_code": ErrorCode.FAILED_TO_FETCH_TEAMS,
                    "message": f"Invalid response from OpenDota API: {e}",
                    "details": {"url": request.path},
                }
            ),
            502,
        )

    if not teams_data:
        return jsonify({"count": 0, "message": "No teams data available"}), 200

    # Store to database
    try:
        count = store_teams(teams_data)
        return jsonify({"count": count, "message": f"Stored {count} teams"}), 200
    except Exception as e:
        return (
            jsonify(
                {
                    "error_code": ErrorCode.FAILED_TO_STORE_TEAMS,
                    "message": f"Failed to store teams: {e!s}",
                    "details": {"url": request.path},
                }
            ),
            500,
        )


@bp.route("/teams/search", methods=["GET"])
def search_teams():
    """Search for teams by name for autocomplete.

    Query parameters:
      - q: Search query (minimum 2 characters)
      - limit: Maximum number of results (default: 10, max: 50)

    Returns:
      - 200: JSON array of matching teams with {team_id, name, tag, logo_url, rating}
      - 400: Missing or invalid query parameter
      - 503: Database connection error
    """
    from backend.db import get_db

    search_query = request.args.get("q", "").strip()
    limit_param = request.args.get("limit", 10)
    try:
        limit = min(int(limit_param), 50)  # Cap at 50
    except (TypeError, ValueError):
        return (
            jsonify(
                {
                    "error_code": ErrorCode.INVALID_REQUEST,
                    "message": "Limit parameter must be a valid integer",
                }
            ),
            400,
        )

    # Validate search query
    if not search_query or len(search_query) < 2:
        return (
            jsonify(
                {
                    "error_code": ErrorCode.INVALID_REQUEST,
                    "message": "Search query must be at least 2 characters",
                }
            ),
            400,
        )

    try:
        db = get_db()
        cursor = db.cursor()

        # Search teams by name or tag (case-insensitive)
        # Prioritize teams that start with the query, then those containing it
        cursor.execute(
            """
            SELECT team_id, name, tag, logo_url, rating
            FROM teams
            WHERE LOWER(name) LIKE LOWER(?) OR LOWER(tag) LIKE LOWER(?)
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
                f"{search_query}%",  # Starts with
                f"%{search_query}%",  # Contains
                f"{search_query}%",
                f"{search_query}%",
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
                    "error_code": ErrorCode.SEARCH_ERROR,
                    "message": "Failed to search teams",
                    "details": {"url": request.path},
                }
            ),
            503,
        )


if __name__ == "__main__":
    from backend import create_app

    app = create_app()
    app.run(debug=True)

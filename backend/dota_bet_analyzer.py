import json
import time

import redis
from celery import Celery  # type: ignore[import-untyped]
from flask import Blueprint, Response, jsonify, request, stream_with_context

from backend.config import Config
from backend.pro_players import fetch_pro_players_from_api, store_pro_players
from backend.stats import compute_statistics, get_matches

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

def update_progress(task_id, step, message, progress, data=None):
    """Update task progress in Redis.
    
    Args:
        task_id: Unique task identifier
        step: Current step number
        message: Progress message
        progress: Progress percentage (0-100) or -1 for error
        data: Additional data to store (optional)
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
    except Exception as e:
        # Log error but don't fail the task if Redis is unavailable
        print(f"Warning: Failed to update progress for task {task_id}: {e}")

@celery.task(bind=True)
def players_statistics_task(self, task_id, accounts: list[int], days: int = 20):
    """Celery task to fetch match statistics for multiple players.
    
    Args:
        task_id: Unique task identifier for progress tracking
        accounts: List of account IDs to fetch statistics for
        days: Number of days of match history to fetch
    """
    try:
        steps: int = 2 + len(accounts)  # Initial + per-account + final
        step_num: int = 0

        update_progress(
            task_id,
            step_num,
            f"Initializing match history fetch for {len(accounts)} players",
            100 * (step_num / steps),
        )

        results = []
        matches_stats = []
        for account_id in accounts:
            step_num += 1
            try:
                # Fetch match data for this account
                players_statistics = get_matches(account_id=account_id, days=days)

                # Convert MatchStats objects to dicts for JSON serialization
                stats_data = [stat.model_dump() for stat in players_statistics]
                matches_stats.append(stats_data)

                results.append({
                    "account_id": account_id,
                    "match_count": len(stats_data),
                    "matches": stats_data,
                })

                update_progress(
                    task_id,
                    step_num,
                    f"Fetched {len(stats_data)} matches for account {account_id}",
                    100 * (step_num / steps),
                    {"account_id": account_id, "match_count": len(stats_data)},
                )
            except Exception as e:
                # Handle per-account errors gracefully
                results.append({
                    "account_id": account_id,
                    "error": str(e),
                })

                update_progress(
                    task_id,
                    step_num,
                    f"Error fetching data for account {account_id}: {e!s}",
                    100 * (step_num / steps),
                    {"account_id": account_id, "error": str(e)},
                )

            time.sleep(0.01)  # Short sleep to prevent overwhelming the API

        step_num += 1        # Final summary
        summary = get_team_matches_summary(matches_stats)


        successful = len([r for r in results if "error" not in r])
        update_progress(
            task_id,
            steps,
            f"Completed: fetched data for {successful}/{len(accounts)} players",
            100,
            {"results": results, "successful": successful, "total": len(accounts)},
        )

    except Exception as exc:
        update_progress(task_id, -1, f"Task error: {exc!s}", -1, {"error": True})
        raise


@bp.route("/statistics/players", methods=["GET"])
def players_statistics():
    """Start calculation and return task ID"""
    try:
        if request.method == "GET":
            accounts = request.args.getlist("account_id")
            days: int = int(request.args.get("days", 20))

        if not accounts:
            return jsonify({"error": "no account_ids provided"}), 400
        if len(accounts) > 10:
            return jsonify({"error": "too many players (account_ids) in the team (max 10)"}), 400

        # Convert accounts to integers and filter valid ones
        accounts_int = []
        for a in accounts:
            if isinstance(a, str):
                a = a.strip()
                try:
                    accounts_int.append(int(a))
                except ValueError:
                    return jsonify({"error": f"Invalid account_id: {a}"}), 400

        if not accounts_int:
            return jsonify({"error": "no valid account_ids provided"}), 400

        try:
            task = players_statistics_task.delay(task_id := f"task_{int(time.time())}", accounts=accounts_int, days=days)
            return jsonify({"status": "started", "task_id": task_id, "celery_task_id": task.id})
        except Exception as e:
            return jsonify({"error": f"Failed to start task: {e!s}"}), 500

    except Exception as e:
        return jsonify({"error": f"Invalid request: {e!s}"}), 400




@bp.route("/stream-progress/<task_id>")
def stream_progress(task_id):
    """Stream progress updates"""

    def generate():
        """Yield Server-Sent Events with progress updates for a task.

        Reads progress snapshots from Redis and emits them as SSE messages
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
                    yield f"data: {json.dumps(current_data)}\n\n"
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


@bp.route("/statistics", methods=["GET", "POST"])
def statistics():
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
            return jsonify({"error": "no teams provided"}), 400
        teams = body.get("teams") or []
    else:
        return jsonify({"error": "unsupported method"}), 400

    # Normalize & validate
    teams = [t.strip() for t in teams if isinstance(t, str) and t.strip()]
    if not teams:
        return jsonify({"error": "no teams provided"}), 400
    if len(teams) > 10:
        return jsonify({"error": "too many teams (max 10)"}), 400

    stats = compute_statistics(teams)
    return jsonify(stats.model_dump())


@bp.route("/ProPlayers", methods=["GET"])
def pro_players():
    """Fetch pro players from OpenDota API and store in database.

    Returns:
        JSON response with status and count of players stored.
    """
    # Fetch data from OpenDota API
    players_data = fetch_pro_players_from_api()

    if players_data is None:
        return jsonify({"error": "Failed to fetch pro players from OpenDota API"}), 500

    if not players_data:
        return jsonify({"status": "ok", "count": 0, "message": "No pro players data available"}), 200

    # Store to database
    try:
        count = store_pro_players(players_data)
        return jsonify({"status": "ok", "count": count, "message": f"Stored {count} pro players"}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to store pro players: {e!s}"}), 500


if __name__ == "__main__":
    from backend import create_app

    app = create_app()
    app.run(debug=True)

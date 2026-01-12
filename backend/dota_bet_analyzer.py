import json
import time

import redis
from celery import Celery  # type: ignore[import-untyped]
from flask import Blueprint, Response, jsonify, request, stream_with_context

from backend.config import Config
from backend.pro_players import fetch_pro_players_from_api, store_pro_players
from backend.stats import compute_statistics

bp = Blueprint("dota", __name__)

# Initialize Celery without app-specific config; the app factory will update it
celery = Celery(__name__)

# Redis for progress storage
redis_client = redis.Redis(host=Config.REDIS_HOST, port=Config.REDIS_PORT, db=1)


@celery.task(bind=True)
def heavy_calculation_task(self, task_id):
    """Celery task for heavy calculation"""

    def update_progress(step, message, progress, data=None):
        progress_data = {
            "step": step,
            "message": message,
            "progress": progress,
            "data": data or {},
            "timestamp": time.time(),
        }
        redis_client.setex(f"progress:{task_id}", 3600, json.dumps(progress_data))  # Expire after 1 hour

    try:
        # First update - almost instant
        update_progress(1, "Initial processing complete", 10, {"initial_result": "Quick calculation done"})

        # Simulate your heavy calculations
        calculations = [
            (2, "Processing data chunk 1...", 30, {"chunk1": "result1"}),
            (3, "Processing data chunk 2...", 50, {"chunk2": "result2"}),
            (4, "Finalizing calculations...", 75, {"chunk3": "result3"}),
            (5, "Calculation complete!", 100, {"final": "all_results"}),
        ]

        for step, message, progress, data in calculations:
            # Your actual heavy calculation here
            time.sleep(0.01)  # Short sleep for tests
            update_progress(step, message, progress, data)

    except Exception as exc:
        update_progress(-1, f"Error: {exc!s}", -1, {"error": True})
        raise


@bp.route("/start-calculation")
def start_calculation():
    """Start calculation and return task ID"""
    task = heavy_calculation_task.delay(task_id := f"task_{int(time.time())}")
    return jsonify({"status": "started", "task_id": task_id, "celery_task_id": task.id})


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

import json
import os
import time

from flask import Response, current_app, jsonify, stream_with_context

from backend import __version__
from backend.head_to_head import get_head_to_head
from backend.helpers import Errors, api_error
from backend.heroes import list_heroes
from backend.jobs import (
    JobRunningError,
    UnknownJobError,
    data_status,
    get_job,
    list_job_statuses,
    queue_job,
    queue_job_if_due,
)
from backend.logging_config import setup_logging
from backend.matches import get_matches
from backend.meta import MetaParams, get_meta
from backend.predictions import (
    SnapshotMissingError,
    create_prediction,
    delete_prediction,
    get_prediction,
    list_predictions,
    save_review,
    update_decision,
)
from backend.routes import ApiBlueprint
from backend.routes.statistics import STREAM_MAX_RUNTIME
from backend.schemas import (
    HeadToHeadSchema,
    HeroSchema,
    JobRunQuerySchema,
    JobSchema,
    MatchesSchema,
    MetaQuerySchema,
    MetaSchema,
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
    TeamSchema,
    TeamSearchQuerySchema,
    VersionSchema,
)
from backend.snapshots import get_snapshot, list_snapshots, save_snapshot

# Setup logger
logger = setup_logging(__name__)


bp = ApiBlueprint("dota", __name__, description="Dota 2 Bet Analyzer API")


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


def _sync_teams_if_obsolete() -> None:
    """Update the teams list in the background when it is obsolete (not in tests, which never reach OpenDota)."""
    if not current_app.config.get("TESTING"):
        queue_job_if_due("teams")


@bp.route("/jobs", methods=["GET"])
@bp.response(200, JobSchema(many=True))
@bp.error_response(500, Errors.FAILED_TO_READ_JOBS, "Database operation failed")
def get_jobs() -> tuple[Response, int]:
    """List the background cache jobs with their state and last run.

    No OpenDota request. A job is due when it never succeeded or its last success is older than its limit
    (`next_run` is null then); a failed job is retried on its own after 10 minutes.
    """
    try:
        return jsonify(list_job_statuses()), 200
    except Exception as e:
        return api_error(500, Errors.FAILED_TO_READ_JOBS, e)


# Data status stream: re-read every JOBS_STREAM_INTERVAL s, closed after STREAM_MAX_RUNTIME (the client reopens it)
JOBS_STREAM_INTERVAL = 2.0


def _generate_jobs_stream(max_runtime: float = STREAM_MAX_RUNTIME, interval: float = JOBS_STREAM_INTERVAL):
    """Yield the jobs and budget status (data_status) as one JSON line each time it changes.

    The first line is sent right away. An error ends the stream with one line {"error": message}.

    Args:
        max_runtime: Seconds before the stream ends
        interval: Seconds between two reads

    Yields:
        JSON lines
    """
    start = time.monotonic()
    last_sent: str | None = None
    try:
        while True:
            line = json.dumps(data_status())
            if line != last_sent:
                yield f"{line}\n"
                last_sent = line
            if time.monotonic() - start + interval > max_runtime:
                return
            time.sleep(interval)
    except Exception as e:
        logger.error(f"Jobs stream error: {e}")
        yield f"{json.dumps({'error': str(e)})}\n"


@bp.route("/jobs/stream")
@bp.response(200, description="Stream of JSON lines with the jobs and OpenDota budget status")
def stream_jobs() -> Response:
    """Stream the status of the background cache jobs and today's OpenDota request budget (main page Data line).

    One JSON object per line, sent at once and then each time something changes (checked every 2 s). The stream
    ends after 120 s; clients reopen it. No OpenDota request.

    Each line:
        - `jobs`: the same list as GET /api/jobs
        - `budget.used`: OpenDota requests today (UTC) by every process, null when Redis cannot be reached
        - `budget.limit`: daily budget; background jobs stop when it is used up (0 = no budget)

    An error ends the stream with a line `{"error": "message"}`.
    """
    return Response(
        stream_with_context(_generate_jobs_stream()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "Access-Control-Allow-Origin": "*"},
    )


@bp.route("/jobs/<string:name>/run", methods=["POST"])
@bp.arguments(JobRunQuerySchema, location="query")
@bp.response(202, JobSchema)
@bp.error_response(
    400, Errors.JOB_FULL_NOT_SUPPORTED, "`full=true` was given for a job that has no full run", name="heroes"
)
@bp.error_response(404, Errors.JOB_NOT_FOUND, "No job has this name", name="x")
@bp.error_response(409, Errors.JOB_RUNNING, "The job is already queued or running", name="teams")
@bp.error_response(503, Errors.FAILED_TO_QUEUE_JOB, "Redis or the Celery broker could not be reached", name="teams")
def run_job_now(args: dict, name: str) -> tuple[Response, int]:
    """Queue a background cache job now, even when its data is not stale.

    The job runs on the background worker; GET /api/jobs shows its progress. `full=true` (teams only) fetches every
    OpenDota /teams page (~22 requests) instead of the 2-request incremental update.
    """
    try:
        job = get_job(name)
    except UnknownJobError:
        return api_error(404, Errors.JOB_NOT_FOUND, name=name)
    if args["full"] and job.run_full is None:
        return api_error(400, Errors.JOB_FULL_NOT_SUPPORTED, name=name)
    try:
        return jsonify(queue_job(name, full=args["full"])), 202
    except JobRunningError:
        return api_error(409, Errors.JOB_RUNNING, name=name)
    except Exception as e:
        return api_error(503, Errors.FAILED_TO_QUEUE_JOB, e, name=name)


@bp.route("/heroes", methods=["GET"])
@bp.response(200, HeroSchema(many=True))
@bp.error_response(500, Errors.FAILED_TO_READ_HEROES, "Database operation failed")
def get_heroes() -> tuple[Response, int]:
    """List the cached heroes (id, names, icon URL) ordered by display name.

    Reads d2ba.sqlite only, no OpenDota request. The `heroes` cache job refreshes the list weekly, POST
    /jobs/heroes/run on demand.
    """
    try:
        return jsonify(list_heroes()), 200
    except Exception as e:
        return api_error(500, Errors.FAILED_TO_READ_HEROES, e)


@bp.route("/heroes/meta", methods=["GET"])
@bp.arguments(MetaQuerySchema, location="query")
@bp.response(200, MetaSchema)
@bp.error_response(503, Errors.FAILED_TO_FETCH_HERO_STATS, "OpenDota could not be reached or its answer was invalid")
def get_hero_meta(args: dict) -> tuple[Response, int]:
    """Pro meta, ultra meta and pub meta heroes from OpenDota /heroStats (about the last 7 days).

    At most one OpenDota request per hour (cached in Redis), or per minute with `refresh=true`; the thresholds
    are query parameters, so changing them needs no new request.
    """
    try:
        refresh = args.pop("refresh", False)
        return jsonify(get_meta(MetaParams(**args), refresh)), 200
    except ConnectionError as e:
        return api_error(503, Errors.FAILED_TO_FETCH_HERO_STATS, e)


@bp.route("/matches", methods=["GET"])
@bp.response(200, MatchesSchema)
@bp.error_response(503, Errors.FAILED_TO_FETCH_MATCHES, "Liquipedia could not be reached or its page could not be read")
@bp.error_response(500, Errors.UNEXPECTED_ERROR, "Database error")
def list_matches() -> tuple[Response, int]:
    """Upcoming (soonest first) and recently finished (newest first) pro series from Liquipedia.

    One Liquipedia request at most every 10 minutes (cached in Redis). Teams are matched by
    name to the teams table for their OpenDota ID and logo; an obsolete teams list is updated in the background.
    """
    _sync_teams_if_obsolete()
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
@bp.error_response(422, Errors.VALIDATION_ERROR, "Invalid query parameters")
@bp.error_response(503, Errors.SEARCH_ERROR, "Database connection error")
def search_teams(args):
    """Search for teams by name or tag for autocomplete.

    Returns a list of matching teams ordered by relevance (starts-with matches first).
    """
    from backend.db import get_cache_db

    _sync_teams_if_obsolete()
    search_query = args["q"]
    limit = args.get("limit", 10)

    try:
        db = get_cache_db()
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
@bp.error_response(422, Errors.TEAM_ID_MISMATCH, "Invalid body, or team_id differs from team.team_id")
@bp.error_response(500, Errors.FAILED_TO_STORE_SNAPSHOT, "Database error")
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
@bp.error_response(422, Errors.VALIDATION_ERROR, "Invalid query parameters")
@bp.error_response(500, Errors.FAILED_TO_READ_SNAPSHOTS, "Database error")
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
@bp.error_response(404, Errors.SNAPSHOT_NOT_FOUND, "Snapshot not found", snapshot_id=1)
@bp.error_response(500, Errors.FAILED_TO_READ_SNAPSHOTS, "Database error")
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
@bp.error_response(404, Errors.SNAPSHOT_NOT_FOUND, "Snapshot not found", snapshot_id=1)
@bp.error_response(422, Errors.VALIDATION_ERROR, "Invalid body")
@bp.error_response(500, Errors.FAILED_TO_STORE_PREDICTION, "Database error")
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
@bp.error_response(422, Errors.VALIDATION_ERROR, "Invalid query parameters")
@bp.error_response(500, Errors.FAILED_TO_READ_PREDICTIONS, "Database error")
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
@bp.error_response(404, Errors.PREDICTION_NOT_FOUND, "Prediction not found", prediction_id=1)
@bp.error_response(500, Errors.FAILED_TO_READ_PREDICTIONS, "Database error")
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
@bp.error_response(404, Errors.PREDICTION_NOT_FOUND, "Prediction not found", prediction_id=1)
@bp.error_response(500, Errors.FAILED_TO_READ_PREDICTIONS, "Database error")
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
@bp.error_response(404, Errors.PREDICTION_NOT_FOUND, "Prediction not found", prediction_id=1)
@bp.error_response(422, Errors.INVALID_RESULT, "Invalid body, or the score does not fit best_of")
@bp.error_response(500, Errors.FAILED_TO_STORE_PREDICTION, "Database error")
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
@bp.error_response(404, Errors.PREDICTION_NOT_FOUND, "Prediction not found", prediction_id=1)
@bp.error_response(422, Errors.INVALID_RESULT, "Invalid body, or the saved result does not fit the new best_of")
@bp.error_response(500, Errors.FAILED_TO_STORE_PREDICTION, "Database error")
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
@bp.error_response(404, Errors.PREDICTION_NOT_FOUND, "Prediction not found", prediction_id=1)
@bp.error_response(500, Errors.FAILED_TO_STORE_PREDICTION, "Database error")
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

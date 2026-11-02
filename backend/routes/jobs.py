"""Cache job routes: job statuses, the Data status stream and manual runs."""

import json
import time

from flask import Response, jsonify, stream_with_context

from backend.helpers import Errors, api_error
from backend.jobs import (
    JobRunningError,
    UnknownJobError,
    data_status,
    get_job,
    list_job_statuses,
    queue_job,
)
from backend.logging_config import setup_logging
from backend.routes import ApiBlueprint
from backend.routes.statistics import STREAM_MAX_RUNTIME
from backend.schemas import JobRunQuerySchema, JobSchema

logger = setup_logging(__name__)


bp = ApiBlueprint("Jobs", __name__, description="Cache jobs: statuses, Data status stream, manual runs")


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

"""The Celery app shared by the Flask backend and the workers.

Two queues: the default one for Compare (players_statistics_task) and `background` for cache jobs (backend.jobs),
each served by its own worker, so a Compare never waits behind a long cache job. Celery Beat sends the due-jobs
check (backend.jobs.check_due_jobs_task) every CHECK_DUE_JOBS_INTERVAL seconds.
"""

from celery import Celery  # type: ignore[import-untyped]

from backend.config import Config

BACKGROUND_QUEUE = "background"  # Queue of the cache jobs, served by the second worker of `npm run dev`
CHECK_DUE_JOBS_INTERVAL = 60  # seconds

celery = Celery("backend.dota_bet_analyzer")

celery.conf.update(
    broker_url=Config.CELERY_BROKER_URL,
    result_backend=Config.CELERY_RESULT_BACKEND,
    beat_schedule={
        "check-due-jobs": {
            "task": "backend.jobs.check_due_jobs_task",
            "schedule": CHECK_DUE_JOBS_INTERVAL,
            # A check waiting behind a long job is dropped once the next one is sent
            "options": {"queue": BACKGROUND_QUEUE, "expires": CHECK_DUE_JOBS_INTERVAL},
        }
    },
)

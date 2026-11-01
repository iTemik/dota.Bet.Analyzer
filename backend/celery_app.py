"""The Celery app shared by the Flask backend and the workers.

Two queues: the default one for Compare (players_statistics_task) and `background` for cache jobs (backend.jobs),
each served by its own worker, so a Compare never waits behind a long cache job.
"""

from celery import Celery  # type: ignore[import-untyped]

from backend.config import Config

BACKGROUND_QUEUE = "background"  # Queue of the cache jobs, served by the second worker of `npm run dev`

celery = Celery("backend.dota_bet_analyzer")

# Redis connection: redis://localhost:6379/0
celery.conf.update(
    broker_url=f"redis://{Config.REDIS_HOST}:{Config.REDIS_PORT}/0",
    result_backend=f"redis://{Config.REDIS_HOST}:{Config.REDIS_PORT}/0",
)

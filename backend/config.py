import os


class Config:
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    DATABASE_FILENAME = os.getenv("DATABASE_FILENAME", "d2ba.sqlite")
    # OpenDota pace shared by all processes: seconds between requests and requests per UTC day before background
    # cache syncs stop (0 = no budget). The free tier allows about 60 requests per minute.
    OPENDOTA_MIN_INTERVAL = float(os.getenv("OPENDOTA_MIN_INTERVAL", "1.2"))
    OPENDOTA_DAILY_LIMIT = int(os.getenv("OPENDOTA_DAILY_LIMIT", "1800"))
    # Liquipedia API terms: at most one parse request per 30 seconds
    LIQUIPEDIA_MIN_INTERVAL = float(os.getenv("LIQUIPEDIA_MIN_INTERVAL", "30"))

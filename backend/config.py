import os


class Config:
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    # OpenDota limit shared by all processes: at most RATE_LIMIT requests in any RATE_WINDOW seconds (bursts allowed
    # until the window is full), and requests per UTC day before background cache syncs stop (0 = no budget).
    # The free tier allows about 60 requests per minute.
    OPENDOTA_RATE_LIMIT = int(os.getenv("OPENDOTA_RATE_LIMIT", "50"))
    OPENDOTA_RATE_WINDOW = float(os.getenv("OPENDOTA_RATE_WINDOW", "60"))
    OPENDOTA_DAILY_LIMIT = int(os.getenv("OPENDOTA_DAILY_LIMIT", "1800"))
    # Liquipedia API terms: at most one parse request per 30 seconds
    LIQUIPEDIA_RATE_WINDOW = float(os.getenv("LIQUIPEDIA_RATE_WINDOW", "30"))

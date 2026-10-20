"""OpenDota HTTP access with a retry when the rate limit is hit.

The free OpenDota tier allows about 60 requests per minute. When it answers HTTP 429 the request
is postponed and repeated a few times instead of failing right away.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Optional

import requests

from backend.logging_config import setup_logging

logger = setup_logging(__name__)

OPENDOTA_API = "https://api.opendota.com/api"
RATE_LIMIT_STATUS = 429
RATE_LIMIT_RETRIES = 3  # Repeats after the first 429 answer
RATE_LIMIT_WAITS = (10, 20, 40)  # Seconds to wait before each repeat when the API gives no Retry-After
RATE_LIMIT_MAX_WAIT = 60  # Never wait longer than this for one repeat

WaitCallback = Callable[[int], None]


def _retry_delay(resp: requests.Response, attempt: int) -> int:
    """Seconds to wait before repeating a rate-limited request (Retry-After header when present)."""
    retry_after = resp.headers.get("Retry-After") if resp.headers else None
    try:
        if retry_after is not None:
            return max(1, min(int(retry_after), RATE_LIMIT_MAX_WAIT))
    except (TypeError, ValueError):
        pass
    return RATE_LIMIT_WAITS[min(attempt, len(RATE_LIMIT_WAITS) - 1)]


def opendota_get(
    url: str,
    params: Optional[dict[str, Any]] = None,
    timeout: float = 30,
    on_wait: Optional[WaitCallback] = None,
) -> requests.Response:
    """GET an OpenDota URL, postponing and repeating the request when the rate limit is hit.

    Args:
        url: URL to fetch
        params: Optional query parameters
        timeout: Request timeout in seconds
        on_wait: Called with the delay in seconds before each repeat (e.g. to report progress)

    Returns:
        The last response (still HTTP 429 when every repeat was rate-limited)

    Raises:
        requests.RequestException: On network errors
    """
    kwargs: dict[str, Any] = {"timeout": timeout}
    if params is not None:
        kwargs["params"] = params
    attempt = 0
    while True:
        resp = requests.get(url, **kwargs)
        if resp.status_code != RATE_LIMIT_STATUS or attempt >= RATE_LIMIT_RETRIES:
            return resp
        delay = _retry_delay(resp, attempt)
        attempt += 1
        logger.warning(f"OpenDota rate limit reached for {url}, retry {attempt}/{RATE_LIMIT_RETRIES} in {delay}s")
        if on_wait is not None:
            on_wait(delay)
        time.sleep(delay)

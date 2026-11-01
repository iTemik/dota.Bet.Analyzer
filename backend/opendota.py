"""OpenDota HTTP access shared by every OpenDota request in the app.

OpenDota limits requests in several ways: HTTP 429 when the per-minute limit is used up (the free tier allows
about 60 requests per minute), HTTP 403 when requests are blocked for a while, and requests that time out or get
the connection dropped when requests come too often in a short time window. In all these cases the request is
postponed and repeated a few times instead of failing right away.

To stay under those limits, every request first takes a slot from one rate limiter shared by all processes
(backend.rate_limit): by default at most 50 requests in any 60 s (bursts allowed) and a daily budget, set in
Config. Background requests (cache syncs) pass `background=True`: they go after user requests and stop when the
daily budget is used up.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Optional

import requests

from backend.config import Config
from backend.logging_config import setup_logging
from backend.rate_limit import DailyLimitReached, RateLimiter, wait_reporter

logger = setup_logging(__name__)

OPENDOTA_API = "https://api.opendota.com/api"
RATE_LIMIT_STATUSES = (403, 429)  # Answers that mean the limit was reached
RATE_LIMIT_RETRIES = 3  # Repeats after the first rate-limited answer or timeout
RATE_LIMIT_WAITS = (10, 20, 40)  # Seconds to wait before each repeat when the API gives no Retry-After
RATE_LIMIT_MAX_WAIT = 60  # Never wait longer than this for one repeat
RETRY_ERRORS = (requests.Timeout, requests.ConnectionError)  # Short-window protection: no answer instead of 429

RADIANT_SLOT_LIMIT = 128  # player_slot < 128 is Radiant

WaitCallback = Callable[[int], None]

OPENDOTA_LIMITER = RateLimiter(
    "opendota", Config.OPENDOTA_RATE_LIMIT, Config.OPENDOTA_RATE_WINDOW, Config.OPENDOTA_DAILY_LIMIT
)


def is_radiant(player_slot: int) -> bool:
    """Whether an OpenDota player_slot is on the Radiant side."""
    return player_slot < RADIANT_SLOT_LIMIT


class OpenDotaError(Exception):
    """An OpenDota request failed after all repeats.

    Attributes:
        status: HTTP status code (503 for network errors, 502 for invalid JSON)
        code: NETWORK_ERROR, HTTP_ERROR or JSON_DECODE_ERROR
        message: Human-readable error message
    """

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def opendota_url(path: str) -> str:
    """Full OpenDota URL for an API path such as "/teams/123" (full URLs are returned as is)."""
    return path if path.startswith("http") else f"{OPENDOTA_API}{path}"


def _retry_delay(resp: Optional[requests.Response], attempt: int) -> int:
    """Seconds to wait before repeating a request (Retry-After header when present)."""
    retry_after = resp.headers.get("Retry-After") if resp is not None and resp.headers else None
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
    background: bool = False,
) -> requests.Response:
    """GET an OpenDota URL, postponing and repeating the request on HTTP 403/429, timeouts and dropped connections.

    Each attempt first waits for a slot of the shared OpenDota rate limiter.

    Args:
        url: URL or API path (e.g. "/teams/123")
        params: Optional query parameters
        timeout: Request timeout in seconds
        on_wait: Called with the delay in seconds before each repeat or long limiter wait (e.g. to report progress);
            defaults to the backend.rate_limit.report_waits callback
        background: True for cache syncs: they let user requests go first and stop at the daily budget

    Returns:
        The last response (still HTTP 403/429 when every repeat was rate-limited)

    Raises:
        requests.RequestException: On network errors, or a timeout after the last repeat
        DailyLimitReached: For a background request when the daily budget is used up
    """
    url = opendota_url(url)
    on_wait = on_wait or wait_reporter()
    kwargs: dict[str, Any] = {"timeout": timeout}
    if params is not None:
        kwargs["params"] = params
    attempt = 0
    while True:
        resp: Optional[requests.Response] = None
        OPENDOTA_LIMITER.acquire(background=background, on_wait=on_wait)
        try:
            resp = requests.get(url, **kwargs)
        except RETRY_ERRORS as exc:
            if attempt >= RATE_LIMIT_RETRIES:
                raise
            reason = f"no answer ({type(exc).__name__})"
        else:
            if resp.status_code not in RATE_LIMIT_STATUSES or attempt >= RATE_LIMIT_RETRIES:
                return resp
            reason = f"limit reached (HTTP {resp.status_code})"
        delay = _retry_delay(resp, attempt)
        attempt += 1
        logger.warning(f"OpenDota {reason} for {url}, retry {attempt}/{RATE_LIMIT_RETRIES} in {delay}s")
        if on_wait is not None:
            on_wait(delay)
        time.sleep(delay)


def get_json(
    url: str,
    params: Optional[dict[str, Any]] = None,
    timeout: float = 30,
    on_wait: Optional[WaitCallback] = None,
    background: bool = False,
) -> Any:
    """GET an OpenDota URL with the shared repeat rules and return the parsed JSON.

    Args:
        url: URL or API path (e.g. "/teams/123")
        params: Optional query parameters
        timeout: Request timeout in seconds
        on_wait: Called with the delay in seconds before each repeat or long limiter wait
        background: True for cache syncs: they let user requests go first and stop at the daily budget

    Returns:
        Parsed JSON payload

    Raises:
        OpenDotaError: On network errors, non-200 answers, invalid JSON or a used-up daily budget (DAILY_LIMIT, 429)
    """
    try:
        resp = opendota_get(url, params=params, timeout=timeout, on_wait=on_wait, background=background)
    except DailyLimitReached as exc:
        raise OpenDotaError(429, "DAILY_LIMIT", str(exc)) from exc
    except Exception as exc:
        raise OpenDotaError(503, "NETWORK_ERROR", f"Network error fetching data: {exc}") from exc

    if resp.status_code != 200:
        raise OpenDotaError(resp.status_code, "HTTP_ERROR", f"HTTP {resp.status_code} from API")

    try:
        return resp.json()
    except Exception as exc:
        raise OpenDotaError(502, "JSON_DECODE_ERROR", f"Invalid JSON response: {exc}") from exc

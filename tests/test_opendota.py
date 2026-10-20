"""Tests for the shared OpenDota client (backend.opendota)."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from backend.opendota import (
    RATE_LIMIT_RETRIES,
    OpenDotaError,
    get_json,
    opendota_get,
    opendota_url,
)


def _response(payload, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.headers = {}
    return resp


def test_path_is_joined_to_api_url():
    assert opendota_url("/teams/1") == "https://api.opendota.com/api/teams/1"
    assert opendota_url("https://api.opendota.com/api/x") == "https://api.opendota.com/api/x"


def test_timeout_is_repeated_like_rate_limit(no_opendota_retry_wait):
    waits = []
    side_effect = [requests.Timeout("slow"), requests.ConnectionError("reset"), _response([1])]
    with patch("backend.opendota.requests.get", side_effect=side_effect) as mock_get:
        resp = opendota_get("/proPlayers", on_wait=waits.append)
    assert resp.json() == [1]
    assert mock_get.call_count == 3
    assert waits == [10, 20]
    assert no_opendota_retry_wait.call_count == 2


def test_timeout_after_last_repeat_is_raised():
    with patch("backend.opendota.requests.get", side_effect=requests.Timeout("slow")) as mock_get:
        with pytest.raises(requests.Timeout):
            opendota_get("/proPlayers")
    assert mock_get.call_count == RATE_LIMIT_RETRIES + 1


def test_get_json_errors():
    with patch("backend.opendota.requests.get", side_effect=requests.Timeout("slow")):
        with pytest.raises(OpenDotaError) as exc_info:
            get_json("/proPlayers")
    assert (exc_info.value.status, exc_info.value.code) == (503, "NETWORK_ERROR")

    with patch("backend.opendota.requests.get", return_value=_response(None, status=500)):
        with pytest.raises(OpenDotaError) as exc_info:
            get_json("/proPlayers")
    assert (exc_info.value.status, exc_info.value.code) == (500, "HTTP_ERROR")

    bad = _response(None)
    bad.json.side_effect = ValueError("bad")
    with patch("backend.opendota.requests.get", return_value=bad):
        with pytest.raises(OpenDotaError) as exc_info:
            get_json("/proPlayers")
    assert (exc_info.value.status, exc_info.value.code) == (502, "JSON_DECODE_ERROR")

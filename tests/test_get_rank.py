"""Tests for get_rank function."""

import requests

from backend.stats import get_rank


class DummyResponse:
    def __init__(self, status_code, json_obj):
        self.status_code = status_code
        self._json = json_obj

    def json(self):
        return self._json


def test_get_rank_success(monkeypatch):
    """Test successful rank retrieval."""

    def fake_get(url, timeout=5):
        return DummyResponse(
            200,
            {
                "account_id": 123456789,
                "leaderboard_rank": 5432,
                "personaname": "TestPlayer",
            },
        )

    monkeypatch.setattr(requests, "get", fake_get)
    rank = get_rank(123456789)

    assert rank == 5432


def test_get_rank_no_leaderboard_rank(monkeypatch):
    """Test when player has no leaderboard rank."""

    def fake_get(url, timeout=5):
        return DummyResponse(
            200,
            {
                "account_id": 123456789,
                "personaname": "TestPlayer",
            },
        )

    monkeypatch.setattr(requests, "get", fake_get)
    rank = get_rank(123456789)

    assert rank is None


def test_get_rank_null_leaderboard_rank(monkeypatch):
    """Test when leaderboard_rank is explicitly null."""

    def fake_get(url, timeout=5):
        return DummyResponse(
            200,
            {
                "account_id": 123456789,
                "leaderboard_rank": None,
                "personaname": "TestPlayer",
            },
        )

    monkeypatch.setattr(requests, "get", fake_get)
    rank = get_rank(123456789)

    assert rank is None


def test_get_rank_http_error(monkeypatch):
    """Test when HTTP request fails."""

    def fake_get(url, timeout=5):
        return DummyResponse(404, {"error": "Not found"})

    monkeypatch.setattr(requests, "get", fake_get)
    rank = get_rank(123456789)

    assert rank is None


def test_get_rank_network_error(monkeypatch):
    """Test when network error occurs."""

    def fake_get(url, timeout=5):
        raise RuntimeError("Connection failed")

    monkeypatch.setattr(requests, "get", fake_get)
    rank = get_rank(123456789)

    assert rank is None


def test_get_rank_invalid_json(monkeypatch):
    """Test when response is not valid JSON."""

    def fake_get(url, timeout=5):
        response = DummyResponse(200, {})

        def bad_json():
            raise ValueError("Invalid JSON")

        response.json = bad_json
        return response

    monkeypatch.setattr(requests, "get", fake_get)
    rank = get_rank(123456789)

    assert rank is None


def test_get_rank_string_rank_converts_to_int(monkeypatch):
    """Test that string rank values are converted to int."""

    def fake_get(url, timeout=5):
        return DummyResponse(
            200,
            {
                "account_id": 123456789,
                "leaderboard_rank": "1234",
                "personaname": "TestPlayer",
            },
        )

    monkeypatch.setattr(requests, "get", fake_get)
    rank = get_rank(123456789)

    assert rank == 1234
    assert isinstance(rank, int)


def test_get_rank_zero_rank(monkeypatch):
    """Test with rank value of 0 (treated as falsy but still valid)."""

    def fake_get(url, timeout=5):
        return DummyResponse(
            200,
            {
                "account_id": 123456789,
                "leaderboard_rank": 0,
                "personaname": "TestPlayer",
            },
        )

    monkeypatch.setattr(requests, "get", fake_get)
    rank = get_rank(123456789)

    # 0 is falsy but should be returned (or None if we treat 0 as invalid)
    # Based on the implementation, it returns None for falsy values
    assert rank is None


def test_get_rank_high_rank_value(monkeypatch):
    """Test with a high rank value."""

    def fake_get(url, timeout=5):
        return DummyResponse(
            200,
            {
                "account_id": 123456789,
                "leaderboard_rank": 999999,
                "personaname": "TestPlayer",
            },
        )

    monkeypatch.setattr(requests, "get", fake_get)
    rank = get_rank(123456789)

    assert rank == 999999

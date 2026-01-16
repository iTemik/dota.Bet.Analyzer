"""Tests for get_matches function."""

import pytest
import requests

from backend.stats import MatchStats, get_matches


class DummyResponse:
    """Mock response object for testing."""

    def __init__(self, status_code, json_obj):
        self.status_code = status_code
        self._json = json_obj

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code != 200:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def test_get_matches_success(monkeypatch):
    """Test successful match fetching."""

    def fake_get(url, timeout=10):
        return DummyResponse(
            200,
            [
                {
                    "match_id": 8645473240,
                    "player_slot": 130,
                    "radiant_win": False,
                    "game_mode": 2,
                    "lobby_type": 1,
                    "hero_id": 59,
                    "average_rank": 75,
                },
                {
                    "match_id": 8645473241,
                    "player_slot": 2,
                    "radiant_win": True,
                    "game_mode": 4,
                    "lobby_type": 7,
                    "hero_id": 1,
                    "average_rank": 80,
                },
            ],
        )

    monkeypatch.setattr(requests, "get", fake_get)

    matches = get_matches(account_id=123456, days=90)

    assert len(matches) == 2
    assert isinstance(matches[0], MatchStats)
    assert matches[0].match_id == 8645473240
    assert matches[0].player_slot == 130
    assert matches[0].radiant_win is False
    assert matches[0].game_mode == 2
    assert matches[0].lobby_type == 1
    assert matches[0].hero_id == 59
    assert matches[0].average_rank == 75

    assert matches[1].match_id == 8645473241
    assert matches[1].hero_id == 1
    assert matches[1].radiant_win is True


def test_get_matches_empty_response(monkeypatch):
    """Test handling empty match list."""

    def fake_get(url, timeout=10):
        return DummyResponse(200, [])

    monkeypatch.setattr(requests, "get", fake_get)

    matches = get_matches(account_id=123456)

    assert isinstance(matches, list)
    assert len(matches) == 0


def test_get_matches_invalid_account_id():
    """Test ValueError for invalid account_id."""

    with pytest.raises(ValueError, match="account_id must be a non-negative integer"):
        get_matches(account_id=-1)

    with pytest.raises(ValueError, match="account_id must be a non-negative integer"):
        get_matches(account_id="invalid")  # type: ignore


def test_get_matches_network_error(monkeypatch):
    """Test handling of network errors."""

    def fake_get(url, timeout=10):
        raise requests.ConnectionError("Network error")

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(requests.RequestException, match="Failed to fetch matches"):
        get_matches(account_id=123456)


def test_get_matches_http_error(monkeypatch):
    """Test handling of HTTP errors."""

    def fake_get(url, timeout=10):
        response = DummyResponse(500, {})
        response.raise_for_status()
        return response

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(requests.RequestException, match="Failed to fetch matches"):
        get_matches(account_id=123456)


def test_get_matches_json_decode_error(monkeypatch):
    """Test handling of invalid JSON response."""

    def fake_get(url, timeout=10):
        response = DummyResponse(200, None)

        def bad_json():
            raise ValueError("Invalid JSON")

        response.json = bad_json
        return response

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(requests.RequestException, match="Failed to fetch matches"):
        get_matches(account_id=123456)


def test_get_matches_non_list_response(monkeypatch):
    """Test handling of non-list response."""

    def fake_get(url, timeout=10):
        return DummyResponse(200, {"error": "Invalid response"})

    monkeypatch.setattr(requests, "get", fake_get)

    matches = get_matches(account_id=123456)

    assert len(matches) == 0


def test_get_matches_malformed_entries(monkeypatch):
    """Test that malformed match entries are skipped."""

    def fake_get(url, timeout=10):
        return DummyResponse(
            200,
            [
                {
                    "match_id": 8645473240,
                    "player_slot": 130,
                    "radiant_win": False,
                    "game_mode": 2,
                    "lobby_type": 1,
                    "hero_id": 59,
                    "average_rank": 75,
                },
                {
                    # Missing required fields
                    "match_id": 8645473241,
                },
                {
                    "match_id": 8645473242,
                    "player_slot": 2,
                    "radiant_win": True,
                    "game_mode": 4,
                    "lobby_type": 7,
                    "hero_id": 1,
                    "average_rank": 80,
                },
            ],
        )

    monkeypatch.setattr(requests, "get", fake_get)

    matches = get_matches(account_id=123456)

    # Should have 2 valid matches, skipping the malformed one
    assert len(matches) == 2
    assert matches[0].match_id == 8645473240
    assert matches[1].match_id == 8645473242


def test_get_matches_optional_average_rank(monkeypatch):
    """Test that average_rank is optional."""

    def fake_get(url, timeout=10):
        return DummyResponse(
            200,
            [
                {
                    "match_id": 8645473240,
                    "player_slot": 130,
                    "radiant_win": False,
                    "game_mode": 2,
                    "lobby_type": 1,
                    "hero_id": 59,
                    # No average_rank
                },
            ],
        )

    monkeypatch.setattr(requests, "get", fake_get)

    matches = get_matches(account_id=123456)

    assert len(matches) == 1
    assert matches[0].average_rank is None


def test_get_matches_custom_days(monkeypatch):
    """Test that custom days parameter is used in URL."""

    captured_url = None

    def fake_get(url, timeout=10):
        nonlocal captured_url
        captured_url = url
        return DummyResponse(200, [])

    monkeypatch.setattr(requests, "get", fake_get)

    get_matches(account_id=123456, days=30)

    assert captured_url is not None
    assert "date=30" in captured_url


def test_get_matches_default_days(monkeypatch):
    """Test default days parameter."""

    captured_url = None

    def fake_get(url, timeout=10):
        nonlocal captured_url
        captured_url = url
        return DummyResponse(200, [])

    monkeypatch.setattr(requests, "get", fake_get)

    get_matches(account_id=123456)

    assert captured_url is not None
    assert "date=20" in captured_url


def test_get_matches_url_format(monkeypatch):
    """Test that correct URL is constructed."""

    captured_url = None

    def fake_get(url, timeout=10):
        nonlocal captured_url
        captured_url = url
        return DummyResponse(200, [])

    monkeypatch.setattr(requests, "get", fake_get)

    account_id = 987654
    days = 60
    get_matches(account_id=account_id, days=days)

    expected = f"https://api.opendota.com/api/players/{account_id}/matches?date={days}"
    assert captured_url == expected

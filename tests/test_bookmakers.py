"""Tests for bookmaker odds (backend.bookmakers) and GET /api/odds/pari."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from backend.bookmakers import (
    CACHE_TTL,
    ERROR_CACHE_TTL,
    PARI_CACHE_KEY,
    PARI_LINE_URLS,
    OddsNotFound,
    find_odds,
    get_pari_series,
    parse_pari_line,
)
from backend.cache import cache_get

START = 1_793_819_700

# Shape of the Pari listBase answer (trimmed): tournaments, series (level 1), a map (level 2), odds per event
LINE = {
    "packetVersion": 1,
    "sports": [
        {"id": 1, "kind": "sport", "name": "Футбол"},
        {"id": 10, "kind": "segment", "name": "Dota 2. EPL Masters. Bo3"},
        {"id": 20, "kind": "segment", "name": "CS2. Major"},
    ],
    "events": [
        {"id": 100, "level": 1, "sportId": 10, "team1": "GamerLegion", "team2": "HULIGANI", "startTime": START},
        {"id": 101, "level": 2, "sportId": 10, "team1": "GamerLegion", "team2": "HULIGANI", "startTime": START},
        {"id": 102, "level": 1, "sportId": 10, "team1": "Team Spirit", "team2": "Xtreme", "startTime": START - 600},
        {"id": 103, "level": 1, "sportId": 10, "team1": "NoOdds", "team2": "Other", "startTime": START},
        {"id": 200, "level": 1, "sportId": 20, "team1": "GamerLegion", "team2": "HULIGANI", "startTime": START},
        {
            "id": 104,
            "level": 1,
            "sportId": 10,
            "team1": "Aurora",
            "team2": "Tundra",
            "startTime": START - 60,
            "place": "live",
        },
    ],
    "customFactors": [
        {"e": 100, "factors": [{"f": 921, "v": 1.3}, {"f": 923, "v": 3.2}, {"f": 1, "v": 1.9, "p": 150}]},
        {"e": 101, "factors": [{"f": 921, "v": 1.5}, {"f": 923, "v": 2.4}]},
        {"e": 102, "factors": [{"f": 921, "v": 1.1}, {"f": 923, "v": 6.0}]},
        {"e": 103, "factors": [{"f": 921, "v": 1.8}]},
        {"e": 200, "factors": [{"f": 921, "v": 2.0}, {"f": 923, "v": 1.7}]},
        {"e": 104, "factors": [{"f": 921, "v": 2.1}, {"f": 923, "v": 1.7}]},
    ],
}


def line_response(data: dict) -> MagicMock:
    """A successful requests response carrying data."""
    response = MagicMock()
    response.json.return_value = data
    return response


def test_parse_keeps_dota_series_with_winner_odds():
    """Only level 1 Dota 2 events with both winner odds, soonest first; maps, other games and partial odds dropped."""
    series = parse_pari_line(LINE)
    assert [(s["team1"], s["team2"]) for s in series] == [
        ("Team Spirit", "Xtreme"),
        ("Aurora", "Tundra"),
        ("GamerLegion", "HULIGANI"),
    ]
    assert series[2] == {
        "team1": "GamerLegion",
        "team2": "HULIGANI",
        "start_time": START,
        "tournament": "Dota 2. EPL Masters. Bo3",
        "live": False,
        "team1_odds": 1.3,
        "team2_odds": 3.2,
    }
    assert series[1]["live"] is True


def test_parse_rejects_answer_without_events():
    """An answer that is not a betting line raises ValueError (cached as a failure)."""
    with pytest.raises(ValueError, match="no events"):
        parse_pari_line({"result": "error"})


def test_find_odds_in_given_order_and_swapped():
    """Teams match in either order; odds and names follow the requested order."""
    series = parse_pari_line(LINE)
    assert find_odds(series, ("GamerLegion", "GL"), ("HULIGANI", None))["team1_odds"] == 1.3
    swapped = find_odds(series, ("HULIGANI", None), ("GamerLegion", None))
    assert (swapped["team1_odds"], swapped["team2_odds"]) == (3.2, 1.3)
    assert swapped["names"] == ["HULIGANI", "GamerLegion"]


def test_find_odds_by_normalized_name_and_tag():
    """ "Spirit" matches "Team Spirit" (normalized) and a tag matches a bookmaker's short name."""
    series = parse_pari_line(LINE)
    assert find_odds(series, ("Spirit", None), ("Xtreme Gaming", "XTREME"))["team2_odds"] == 6.0


def test_find_odds_not_found_lists_series():
    """No series of the pair raises OddsNotFound with what the bookmaker has."""
    with pytest.raises(OddsNotFound) as e:
        find_odds(parse_pari_line(LINE), ("GamerLegion", None), ("Tundra", None))
    assert "GamerLegion vs HULIGANI" in e.value.matches


def test_get_pari_series_caches_dota_part():
    """One request; the parsed Dota part is cached, so the next call sends none."""
    with patch("backend.bookmakers.requests.get", return_value=line_response(LINE)) as get:
        first = get_pari_series()
        second = get_pari_series()
    assert get.call_count == 1
    assert first == second == cache_get(PARI_CACHE_KEY)
    assert get.call_args.args[0] == PARI_LINE_URLS[0]
    assert "Mozilla" in get.call_args.kwargs["headers"]["User-Agent"]
    assert CACHE_TTL > ERROR_CACHE_TTL


def test_get_pari_series_tries_next_server():
    """A failing line server is skipped for the next one."""
    responses = [requests.ConnectionError("down"), line_response(LINE)]
    with patch("backend.bookmakers.requests.get", side_effect=responses) as get:
        assert len(get_pari_series()) == 3
    assert get.call_args.args[0] == PARI_LINE_URLS[1]


def test_get_pari_series_failure_is_cached():
    """When every server fails, the failure is cached so the next press sends no request."""
    with patch("backend.bookmakers.requests.get", side_effect=requests.Timeout("slow")) as get:
        with pytest.raises(ConnectionError):
            get_pari_series()
        with pytest.raises(ConnectionError):
            get_pari_series()
    assert get.call_count == len(PARI_LINE_URLS)


def test_odds_route_200(client):
    """GET /api/odds/pari returns the odds in the requested order."""
    with patch("backend.bookmakers.requests.get", return_value=line_response(LINE)):
        response = client.get("/api/odds/pari?team1=HULIGANI&team2=GamerLegion&tag1=HLG")
    assert response.status_code == 200
    assert response.get_json() == {
        "team1_odds": 3.2,
        "team2_odds": 1.3,
        "start_time": START,
        "tournament": "Dota 2. EPL Masters. Bo3",
        "live": False,
        "names": ["HULIGANI", "GamerLegion"],
    }


def test_odds_route_404(client):
    """No series of the pair: 404 ODDS_NOT_FOUND listing Pari's series."""
    with patch("backend.bookmakers.requests.get", return_value=line_response(LINE)):
        response = client.get("/api/odds/pari?team1=Unknown&team2=GamerLegion")
    body = response.get_json()
    assert response.status_code == 404
    assert body["code"] == "ODDS_NOT_FOUND"
    assert "Aurora vs Tundra" in body["details"]["matches"]


def test_odds_route_422(client):
    """A missing team is a validation error."""
    assert client.get("/api/odds/pari?team1=GamerLegion").status_code == 422


def test_odds_route_503(client):
    """The line could not be loaded: 503 FAILED_TO_FETCH_ODDS."""
    with patch("backend.bookmakers.requests.get", side_effect=requests.ConnectionError("down")):
        response = client.get("/api/odds/pari?team1=A&team2=B")
    assert response.status_code == 503
    assert response.get_json()["code"] == "FAILED_TO_FETCH_ODDS"

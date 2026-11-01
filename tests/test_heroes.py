"""Tests for the hero list: OpenDota /constants/heroes sync, GET /api/heroes and POST /api/heroes/sync."""

import sqlite3
from unittest.mock import patch

import pytest

from backend.heroes import fetch_heroes_from_api, list_heroes
from backend.opendota import OpenDotaError

CONSTANTS_HEROES = {
    "1": {
        "id": 1,
        "name": "npc_dota_hero_antimage",
        "localized_name": "Anti-Mage",
        "primary_attr": "agi",
        "img": "/apps/dota2/images/dota_react/heroes/antimage.png?",
        "icon": "/apps/dota2/images/dota_react/heroes/icons/antimage.png?",
    },
    "2": {
        "id": 2,
        "name": "npc_dota_hero_axe",
        "localized_name": "Axe",
        "icon": "/apps/dota2/images/dota_react/heroes/icons/axe.png?",
    },
    "999": {"id": 999},  # malformed: skipped
}

ANTI_MAGE = {
    "hero_id": 1,
    "name": "npc_dota_hero_antimage",
    "localized_name": "Anti-Mage",
    "icon": "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/icons/antimage.png",
}


@pytest.fixture
def mock_get_json():
    """OpenDota /constants/heroes answer, no real request."""
    with patch("backend.heroes.get_json", return_value=CONSTANTS_HEROES) as mock:
        yield mock


def test_fetch_parses_ids_names_and_full_icon_url(mock_get_json):
    heroes = fetch_heroes_from_api()

    mock_get_json.assert_called_once_with("/constants/heroes", timeout=30, background=False)
    assert heroes[0] == ANTI_MAGE
    assert [h["hero_id"] for h in heroes] == [1, 2]


def test_fetch_rejects_non_object_answer():
    with patch("backend.heroes.get_json", return_value=[]):
        with pytest.raises(ValueError):
            fetch_heroes_from_api()


def test_fetch_network_error_is_connection_error():
    with patch("backend.heroes.get_json", side_effect=OpenDotaError(503, "NETWORK_ERROR", "down")):
        with pytest.raises(ConnectionError):
            fetch_heroes_from_api()


def test_get_heroes_empty(client):
    response = client.get("/api/heroes")

    assert response.status_code == 200
    assert response.get_json() == []


def test_get_heroes_sorted_by_name(app, client, mock_get_json):
    client.post("/api/heroes/sync")

    response = client.get("/api/heroes")

    assert response.status_code == 200
    assert [h["localized_name"] for h in response.get_json()] == ["Anti-Mage", "Axe"]
    assert response.get_json()[0] == ANTI_MAGE


def test_get_heroes_database_error(client):
    with patch("backend.dota_bet_analyzer.list_heroes", side_effect=sqlite3.OperationalError("no such table")):
        response = client.get("/api/heroes")

    assert response.status_code == 500
    assert response.get_json()["code"] == "FAILED_TO_READ_HEROES"


def test_sync_endpoint_refreshes_changed_hero(app, client, mock_get_json):
    client.post("/api/heroes/sync")
    renamed = {"1": {**CONSTANTS_HEROES["1"], "localized_name": "Anti Mage"}}

    with patch("backend.heroes.get_json", return_value=renamed):
        response = client.post("/api/heroes/sync")

    assert response.status_code == 200
    assert response.get_json() == {"synced_count": 1, "message": "Stored 1 heroes"}
    with app.app_context():
        assert [h["localized_name"] for h in list_heroes()] == ["Anti Mage", "Axe"]


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (OpenDotaError(503, "NETWORK_ERROR", "down"), 503),
        (OpenDotaError(502, "JSON_DECODE_ERROR", "bad json"), 502),
    ],
)
def test_sync_endpoint_opendota_errors(client, error, status):
    with patch("backend.heroes.get_json", side_effect=error):
        response = client.post("/api/heroes/sync")

    assert response.status_code == status
    assert response.get_json()["code"] == "FAILED_TO_FETCH_HEROES"


def test_sync_endpoint_database_error(client, mock_get_json):
    with patch("backend.dota_bet_analyzer.store_heroes", side_effect=sqlite3.OperationalError("locked")):
        response = client.post("/api/heroes/sync")

    assert response.status_code == 500
    assert response.get_json()["code"] == "FAILED_TO_STORE_HEROES"

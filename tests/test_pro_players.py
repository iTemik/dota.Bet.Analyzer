"""Tests for pro players endpoint and database operations."""

import json
import os
import sqlite3
import tempfile
from unittest.mock import patch

import pytest
import requests

from backend import create_app
from backend.pro_players import fetch_pro_players_from_api, fetch_teams_from_api
from scripts.init_d2ba_db import init_d2ba_db


@pytest.fixture
def app():
    """Create application for testing."""
    # Create temporary database directory with unique path for each test
    temp_dir = tempfile.mkdtemp()
    custom_instance = tempfile.mkdtemp()

    # Patch the API call to prevent real requests during app startup
    with patch("backend.pro_players.fetch_pro_players_from_api") as mock_fetch:
        mock_fetch.side_effect = ConnectionError("Skipped during test setup")  # Skip startup sync

        app = create_app(
            {
                "TESTING": True,
                "DATABASE": os.path.join(temp_dir, "opendota.sqlite"),
            }
        )

        # Override instance path for d2ba database
        app.instance_path = custom_instance

        # Initialize d2ba database in custom instance path
        d2ba_path = os.path.join(custom_instance, "d2ba.sqlite")
        from scripts.init_d2ba_db import init_d2ba_db

        init_d2ba_db(d2ba_path)

    yield app

    # Cleanup
    import shutil

    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    if os.path.exists(custom_instance):
        shutil.rmtree(custom_instance)


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def sample_pro_players_data():
    """Sample pro players data from OpenDota API."""
    return [
        {
            "account_id": 1296625,
            "steamid": "76561197961562353",
            "avatar": "https://avatars.steamstatic.com/test.jpg",
            "avatarmedium": "https://avatars.steamstatic.com/test_medium.jpg",
            "avatarfull": "https://avatars.steamstatic.com/test_full.jpg",
            "profileurl": "https://steamcommunity.com/id/Newsham/",
            "personaname": "Newsham",
            "last_login": "2025-10-23T08:31:29.662Z",
            "name": "Newsham",
            "country_code": "US",
            "fantasy_role": 2,
            "team_id": 8944221,
            "team_name": "Fart Studios",
            "team_tag": "FRT",
            "is_locked": True,
            "is_pro": True,
            "locked_until": None,
        },
        {
            "account_id": 1234567,
            "steamid": "76561197961234567",
            "profileurl": "https://steamcommunity.com/id/TestPlayer/",
            "personaname": "TestPlayer",
            "name": "Test Player",
            "fantasy_role": 1,
            "team_id": 1111111,
            "team_name": "Test Team",
            "team_tag": "TT",
            "is_pro": True,
        },
    ]


def test_pro_players_endpoint_success(client, sample_pro_players_data):
    """Test /pro-players/sync endpoint with successful API response."""
    with patch("backend.dota_bet_analyzer.fetch_pro_players_from_api") as mock_fetch:
        mock_fetch.return_value = sample_pro_players_data

        response = client.post("/api/pro-players/sync")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["count"] == 2
        assert "Stored 2 pro players" in data["message"]


def test_pro_players_endpoint_stores_data(client, sample_pro_players_data, app):
    """Test that /pro-players/sync actually stores data in database."""
    with patch("backend.dota_bet_analyzer.fetch_pro_players_from_api") as mock_fetch:
        mock_fetch.return_value = sample_pro_players_data

        response = client.post("/api/pro-players/sync")
        assert response.status_code == 200

        # Check database
        with app.app_context():
            from backend.pro_players import get_d2ba_db

            db = get_d2ba_db()
            cursor = db.cursor()
            cursor.execute("SELECT COUNT(*) FROM pro_players")
            count = cursor.fetchone()[0]
            assert count == 2

            # Check specific player data
            cursor.execute("SELECT * FROM pro_players WHERE account_id = ?", (1296625,))
            player = cursor.fetchone()
            assert player is not None
            assert player["personaname"] == "Newsham"
            assert player["team_name"] == "Fart Studios"
            assert player["team_tag"] == "FRT"
            assert player["is_pro"] == 1  # SQLite stores boolean as integer


def test_pro_players_endpoint_connection_failure(client):
    """Test /pro-players/sync endpoint when connection fails."""
    with patch("backend.dota_bet_analyzer.fetch_pro_players_from_api") as mock_fetch:
        mock_fetch.side_effect = ConnectionError("Failed to connect to OpenDota API")

        response = client.post("/api/pro-players/sync")

        assert response.status_code == 503
        data = json.loads(response.data)
        assert "error_code" in data


def test_pro_players_endpoint_invalid_response(client):
    """Test /pro-players/sync endpoint when API returns invalid response."""
    with patch("backend.dota_bet_analyzer.fetch_pro_players_from_api") as mock_fetch:
        mock_fetch.side_effect = ValueError("Invalid response from OpenDota API")

        response = client.post("/api/pro-players/sync")

        assert response.status_code == 502
        data = json.loads(response.data)
        assert "error_code" in data


def test_pro_players_endpoint_empty_response(client):
    """Test /pro-players/sync endpoint with empty array from API."""
    with patch("backend.dota_bet_analyzer.fetch_pro_players_from_api") as mock_fetch:
        mock_fetch.return_value = []

        response = client.post("/api/pro-players/sync")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["count"] == 0


def test_pro_players_upsert(client, sample_pro_players_data, app):
    """Test that updating existing players works (upsert behavior)."""
    with patch("backend.dota_bet_analyzer.fetch_pro_players_from_api") as mock_fetch:
        mock_fetch.return_value = sample_pro_players_data

        # First insert
        client.post("/api/pro-players/sync")

        # Update data
        updated_data = sample_pro_players_data.copy()
        updated_data[0]["team_name"] = "Updated Team"
        updated_data[0]["team_tag"] = "UPD"

        mock_fetch.return_value = updated_data

        # Second insert (should update)
        client.post("/api/pro-players/sync")

        # Check database
        with app.app_context():
            from backend.pro_players import get_d2ba_db

            db = get_d2ba_db()
            cursor = db.cursor()

            # Should still have only 2 players
            cursor.execute("SELECT COUNT(*) FROM pro_players")
            count = cursor.fetchone()[0]
            assert count == 2

            # Check updated data
            cursor.execute("SELECT * FROM pro_players WHERE account_id = ?", (1296625,))
            player = cursor.fetchone()
            assert player["team_name"] == "Updated Team"
            assert player["team_tag"] == "UPD"


def test_store_pro_players_direct():
    """Test store_pro_players function directly."""
    from backend.pro_players import store_pro_players

    # Create temp database
    fd, db_path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)

    try:
        init_d2ba_db(db_path)

        # Create app context
        app = create_app({"TESTING": True})

        with app.app_context():
            # Mock the g.d2ba_db connection
            from flask import g

            g.d2ba_db = sqlite3.connect(db_path)
            g.d2ba_db.row_factory = sqlite3.Row

            players_data = [
                {
                    "account_id": 123,
                    "steamid": "test",
                    "profileurl": "url",
                    "personaname": "persona",
                    "name": "name",
                    "fantasy_role": 1,
                    "team_id": 456,
                    "team_name": "team",
                    "team_tag": "tag",
                    "is_pro": True,
                }
            ]

            count = store_pro_players(players_data)
            assert count == 1

            # Verify in database
            cursor = g.d2ba_db.cursor()
            cursor.execute("SELECT * FROM pro_players WHERE account_id = ?", (123,))
            player = cursor.fetchone()
            assert player is not None
            assert player["name"] == "name"

            g.d2ba_db.close()

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_fetch_pro_players_from_api_integration():
    """Test fetch_pro_players_from_api with mocked requests."""
    sample_data = [{"account_id": 123, "name": "test"}]

    with patch("backend.pro_players.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = sample_data
        mock_get.return_value.raise_for_status.return_value = None

        result = fetch_pro_players_from_api()

        assert result == sample_data
        mock_get.assert_called_once_with("https://api.opendota.com/api/proPlayers", timeout=30)


def test_fetch_pro_players_from_api_connection_error():
    """Test fetch_pro_players_from_api raises ConnectionError on network failure."""
    with patch("backend.pro_players.requests.get") as mock_get:
        mock_get.side_effect = requests.RequestException("Network error")

        with pytest.raises(ConnectionError) as exc_info:
            fetch_pro_players_from_api()

        assert "Failed to fetch pro players" in str(exc_info.value)


def test_fetch_pro_players_from_api_invalid_response():
    """Test fetch_pro_players_from_api raises ValueError for non-list response."""
    with patch("backend.pro_players.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"error": "not a list"}
        mock_get.return_value.raise_for_status.return_value = None

        with pytest.raises(ValueError) as exc_info:
            fetch_pro_players_from_api()

        assert "Expected list" in str(exc_info.value)


def test_get_players_by_team_id(app):
    """Test getting players by team_id."""
    with app.app_context():
        from backend.pro_players import get_d2ba_db, get_players_by_team

        # Insert test data
        db = get_d2ba_db()
        cursor = db.cursor()
        test_players = [
            (1, "76561197961234560", "url", "player1", "Player One", 1, 100, "Team A", "TA", 1),
            (2, "76561197961234561", "url", "player2", "Player Two", 2, 100, "Team A", "TA", 1),
            (3, "76561197961234562", "url", "player3", "Player Three", 1, 200, "Team B", "TB", 0),
        ]

        for player in test_players:
            cursor.execute(
                """INSERT INTO pro_players
                (account_id, steamid, profileurl, personaname, name, fantasy_role, team_id, team_name, team_tag, is_pro)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                player,
            )
        db.commit()

        # Test get_players_by_team_id
        pro_players, other_players = get_players_by_team(team_id=100)
        assert len(pro_players) == 2
        assert len(other_players) == 0
        player_names = [p.name for p in pro_players]
        assert "Player One" in player_names
        assert "Player Two" in player_names
        assert "Player Three" not in player_names
        # Check that Player objects have correct ID
        assert any(p.id == 1 for p in pro_players)
        assert any(p.id == 2 for p in pro_players)


def test_get_players_by_team_name(app):
    """Test getting players by team_name."""
    with app.app_context():
        from backend.pro_players import get_d2ba_db, get_players_by_team

        db = get_d2ba_db()
        cursor = db.cursor()
        test_players = [
            (1, "76561197961234560", "url", "player1", "Player One", 1, 100, "Liquid", "Liquid", 1),
            (2, "76561197961234561", "url", "player2", "Player Two", 2, 100, "Liquid", "Liquid", 1),
            (3, "76561197961234562", "url", "player3", "Player Three", 1, 200, "Secret", "Secret", 0),
        ]

        for player in test_players:
            cursor.execute(
                """INSERT INTO pro_players
                (account_id, steamid, profileurl, personaname, name, fantasy_role, team_id, team_name, team_tag, is_pro)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                player,
            )
        db.commit()

        # Test case-insensitive team_name
        pro_players, other_players = get_players_by_team(team_name="LIQUID")
        assert len(pro_players) == 2
        assert len(other_players) == 0
        player_names = [p.name for p in pro_players]
        assert "Player One" in player_names
        assert "Player Two" in player_names


def test_get_players_by_team_tag(app):
    """Test getting players by team_tag."""
    with app.app_context():
        from backend.pro_players import get_d2ba_db, get_players_by_team

        db = get_d2ba_db()
        cursor = db.cursor()
        test_players = [
            (1, "76561197961234560", "url", "player1", "Player One", 1, 100, "Team A", "TA", 1),
            (2, "76561197961234561", "url", "player2", "Player Two", 2, 100, "Team A", "TA", 1),
            (3, "76561197961234562", "url", "player3", "Player Three", 1, 200, "Team B", "TB", 0),
        ]

        for player in test_players:
            cursor.execute(
                """INSERT INTO pro_players
                (account_id, steamid, profileurl, personaname, name, fantasy_role, team_id, team_name, team_tag, is_pro)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                player,
            )
        db.commit()

        # Test case-insensitive team_tag
        pro_players, other_players = get_players_by_team(team_tag="ta")
        assert len(pro_players) == 2
        assert len(other_players) == 0
        player_names = [p.name for p in pro_players]
        assert "Player One" in player_names
        assert "Player Two" in player_names


def test_get_players_by_team_multiple_criteria(app):
    """Test getting players using multiple criteria (OR logic)."""
    with app.app_context():
        from backend.pro_players import get_d2ba_db, get_players_by_team

        db = get_d2ba_db()
        cursor = db.cursor()
        test_players = [
            (1, "76561197961234560", "url", "player1", "Player One", 1, 100, "Liquid", "Liquid", 1),
            (2, "76561197961234561", "url", "player2", "Player Two", 2, 200, "Secret", "Secret", 0),
        ]

        for player in test_players:
            cursor.execute(
                """INSERT INTO pro_players
                (account_id, steamid, profileurl, personaname, name, fantasy_role, team_id, team_name, team_tag, is_pro)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                player,
            )
        db.commit()

        # Test multiple criteria (team_id=100 OR team_name="Secret")
        pro_players, other_players = get_players_by_team(team_id=100, team_name="Secret")
        assert len(pro_players) == 1  # Player One with is_pro=1
        assert len(other_players) == 1  # Player Two with is_pro=0
        pro_player_names = [p.name for p in pro_players]
        other_player_names = [p.name for p in other_players]
        assert "Player One" in pro_player_names
        assert "Player Two" in other_player_names


def test_get_players_by_team_no_matches(app):
    """Test getting players when no matches found."""
    with app.app_context():
        from backend.pro_players import get_players_by_team

        pro_players, other_players = get_players_by_team(team_id=9999)
        assert pro_players == []
        assert other_players == []


def test_get_players_by_team_no_criteria():
    """Test that ValueError is raised when no criteria provided."""
    from backend.pro_players import get_players_by_team

    with pytest.raises(ValueError, match="At least one search criterion"):
        get_players_by_team()


def test_get_players_by_team_integration_with_stats(app):
    """Test that get_players_by_team works within stats computation."""
    with app.app_context():
        from backend.pro_players import get_d2ba_db, get_players_by_team
        from backend.stats import TeamStats

        # Insert test pro players into database
        db = get_d2ba_db()
        cursor = db.cursor()
        cursor.execute(
            """INSERT INTO pro_players
            (account_id, steamid, profileurl, personaname, name, fantasy_role, team_id, team_name, team_tag, is_pro)
            VALUES (1, '76561197961234560', 'url', 'player1', 'Player One', 1, 123456, 'Test Team', 'TT', 1)"""
        )
        cursor.execute(
            """INSERT INTO pro_players
            (account_id, steamid, profileurl, personaname, name, fantasy_role, team_id, team_name, team_tag, is_pro)
            VALUES (2, '76561197961234561', 'url', 'player2', 'Player Two', 2, 123456, 'Test Team', 'TT', 0)"""
        )
        db.commit()

        # Demonstrate that get_players_by_team returns a tuple of pro_players and other_players
        pro_players, other_players = get_players_by_team(team_id=123456)
        assert len(pro_players) == 1
        assert len(other_players) == 1

        # Create a TeamStats with players populated from database query
        team_stats = TeamStats(
            team_id=123456,
            team="Test Team",
            tag="TT",
            rating=2500.5,
            delta=25.3,
            logo_url="https://example.com/logo.png",
            players=pro_players,
            other_players=other_players,
        )

        assert len(team_stats.players) == 1
        assert team_stats.players[0].name == "Player One"
        assert len(team_stats.other_players) == 1
        assert team_stats.other_players[0].name == "Player Two"


# Tests for Teams Endpoint
@pytest.fixture
def sample_teams_data():
    """Sample team data from OpenDota API."""
    return [
        {
            "team_id": 7119388,
            "rating": 1543.55,
            "wins": 834,
            "losses": 554,
            "last_match_time": 1766341021,
            "delta": -17.9257,
            "match_id": 8615531269,
            "name": "Team Spirit",
            "tag": "TSpirit",
            "logo_url": "https://cdn.steamusercontent.com/ugc/1839179120711951766/CD7E0885CB527334205CC7885E9C101B7BC17702/",
        },
        {
            "team_id": 1375614,
            "rating": 1523.45,
            "wins": 750,
            "losses": 500,
            "last_match_time": 1766340921,
            "delta": -10.5,
            "match_id": 8615531268,
            "name": "Evil Geniuses",
            "tag": "EG",
            "logo_url": "https://example.com/eg.png",
        },
    ]


def test_teams_endpoint_sync_success(client, sample_teams_data):
    """Test /teams/sync endpoint with successful API response."""
    with patch("backend.dota_bet_analyzer.fetch_teams_from_api") as mock_fetch:
        mock_fetch.return_value = sample_teams_data

        response = client.post("/api/teams/sync")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["count"] == 2
        assert "Stored 2 teams" in data["message"]


def test_teams_endpoint_stores_data(client, sample_teams_data, app):
    """Test that /teams/sync actually stores data in database."""
    with patch("backend.dota_bet_analyzer.fetch_teams_from_api") as mock_fetch:
        mock_fetch.return_value = sample_teams_data

        response = client.post("/api/teams/sync")
        assert response.status_code == 200

        # Check database
        with app.app_context():
            from backend.pro_players import get_d2ba_db

            db = get_d2ba_db()
            cursor = db.cursor()
            cursor.execute("SELECT COUNT(*) FROM teams")
            count = cursor.fetchone()[0]
            assert count == 2

            # Check specific team data
            cursor.execute("SELECT * FROM teams WHERE team_id = ?", (7119388,))
            team = cursor.fetchone()
            assert team is not None
            assert team["name"] == "Team Spirit"
            assert team["tag"] == "TSpirit"
            assert team["rating"] == 1543.55
            assert team["logo_url"].startswith("https://cdn.steamusercontent.com")

            # Verify that unwanted fields are NOT stored
            assert "wins" not in dict(team).keys()
            assert "losses" not in dict(team).keys()
            assert "delta" not in dict(team).keys()


def test_teams_endpoint_api_failure(client):
    """Test /teams/sync endpoint when OpenDota API fails."""
    with patch("backend.dota_bet_analyzer.fetch_teams_from_api") as mock_fetch:
        mock_fetch.side_effect = ConnectionError("Failed to connect to OpenDota API")

        response = client.post("/api/teams/sync")

        assert response.status_code == 503
        data = json.loads(response.data)
        assert "error_code" in data


def test_teams_endpoint_invalid_response(client):
    """Test /teams/sync endpoint when API returns invalid response."""
    with patch("backend.dota_bet_analyzer.fetch_teams_from_api") as mock_fetch:
        mock_fetch.side_effect = ValueError("Invalid response from OpenDota API")

        response = client.post("/api/teams/sync")

        assert response.status_code == 502
        data = json.loads(response.data)
        assert "error_code" in data


def test_teams_endpoint_empty_response(client):
    """Test /teams/sync endpoint with empty array from API."""
    with patch("backend.dota_bet_analyzer.fetch_teams_from_api") as mock_fetch:
        mock_fetch.return_value = []

        response = client.post("/api/teams/sync")

        assert response.status_code == 200
        data = json.loads(response.data)

        assert data["count"] == 0


def test_teams_upsert(client, sample_teams_data, app):
    """Test that updating existing teams works (upsert behavior)."""
    with patch("backend.dota_bet_analyzer.fetch_teams_from_api") as mock_fetch:
        mock_fetch.return_value = sample_teams_data

        # First insert
        client.post("/api/teams/sync")

        # Update data
        updated_data = sample_teams_data.copy()
        updated_data[0]["rating"] = 1600.0
        updated_data[0]["name"] = "Team Spirit Updated"

        mock_fetch.return_value = updated_data

        # Second insert (should update)
        client.post("/api/teams/sync")

        # Check database
        with app.app_context():
            from backend.pro_players import get_d2ba_db

            db = get_d2ba_db()
            cursor = db.cursor()

            # Should still have 2 teams (upserted, not inserted again)
            cursor.execute("SELECT COUNT(*) FROM teams")
            count = cursor.fetchone()[0]
            assert count == 2

            # Check updated values
            cursor.execute("SELECT * FROM teams WHERE team_id = ?", (7119388,))
            team = cursor.fetchone()
            assert team["rating"] == 1600.0
            assert team["name"] == "Team Spirit Updated"


@patch("backend.pro_players.requests.get")
def test_fetch_teams_from_api_pagination(mock_get, sample_teams_data):
    """Test that fetch_teams_from_api handles pagination correctly."""
    # Create mock responses: first page with 1000 items, second with 2
    page_1 = sample_teams_data * 500  # 1000 items
    page_2 = sample_teams_data  # 2 items (less than 1000, triggers stop)

    # Setup mock to return different data for each page
    mock_response_1 = type("Response", (), {"json": lambda self: page_1, "raise_for_status": lambda self: None})()
    mock_response_2 = type("Response", (), {"json": lambda self: page_2, "raise_for_status": lambda self: None})()

    mock_get.side_effect = [mock_response_1, mock_response_2]

    result = fetch_teams_from_api()

    assert result is not None
    assert isinstance(result, list)
    assert len(result) == 1002  # 1000 + 2
    # Verify API was called twice (page 0 and page 1)
    assert mock_get.call_count == 2


@patch("backend.pro_players.requests.get")
def test_fetch_teams_from_api_connection_error(mock_get):
    """Test that fetch_teams_from_api raises ConnectionError on first page failure."""
    mock_get.side_effect = requests.RequestException("Network error")

    with pytest.raises(ConnectionError) as exc_info:
        fetch_teams_from_api()

    assert "Failed to fetch teams" in str(exc_info.value)


@patch("backend.pro_players.requests.get")
def test_fetch_teams_from_api_invalid_response(mock_get):
    """Test that fetch_teams_from_api raises ValueError for non-list response."""
    mock_response = type(
        "Response", (), {"json": lambda self: {"error": "not a list"}, "raise_for_status": lambda self: None}
    )()
    mock_get.return_value = mock_response

    with pytest.raises(ValueError) as exc_info:
        fetch_teams_from_api()

    assert "Expected list" in str(exc_info.value)


@patch("backend.pro_players.requests.get")
def test_fetch_teams_from_api_partial_failure_graceful_degradation(mock_get, sample_teams_data):
    """Test that fetch_teams_from_api returns partial data if later pages fail."""
    # First page succeeds, second page fails
    page_1 = sample_teams_data * 500  # 1000 items
    mock_response_1 = type("Response", (), {"json": lambda self: page_1, "raise_for_status": lambda self: None})()

    mock_get.side_effect = [mock_response_1, requests.RequestException("Network error on page 2")]

    # Should return partial data from page 1, not raise exception
    result = fetch_teams_from_api()

    assert result is not None
    assert len(result) == 1000  # Only page 1 data


def test_teams_endpoint_with_large_dataset(client, sample_teams_data, app):
    """Test /teams/sync endpoint with larger dataset."""
    # Create 1500 unique teams (more than one page)
    large_dataset = []
    for i in range(1500):
        large_dataset.append(
            {
                "team_id": 1000000 + i,
                "rating": 1500.0 + i,
                "wins": 100 + i,
                "losses": 50 + i,
                "last_match_time": 1766341021 + i,
                "delta": -10.0,
                "match_id": 8615531269 + i,
                "name": f"Team {i}",
                "tag": f"T{i}",
                "logo_url": f"https://example.com/team_{i}.png",
            }
        )

    with patch("backend.dota_bet_analyzer.fetch_teams_from_api") as mock_fetch:
        mock_fetch.return_value = large_dataset

        response = client.post("/api/teams/sync")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["count"] == 1500

        # Verify all teams are stored
        with app.app_context():
            from backend.pro_players import get_d2ba_db

            db = get_d2ba_db()
            cursor = db.cursor()
            cursor.execute("SELECT COUNT(*) FROM teams")
            count = cursor.fetchone()[0]
            assert count == 1500

"""Tests for pro players endpoint and database operations."""

import json
import os
import sqlite3
import tempfile
from unittest.mock import patch

import pytest

from backend import create_app
from scripts.init_d2ba_db import init_d2ba_db


@pytest.fixture
def app():
    """Create application for testing."""
    # Create temporary database directory with unique path for each test
    temp_dir = tempfile.mkdtemp()
    custom_instance = tempfile.mkdtemp()

    # Patch the API call to prevent real requests during app startup
    with patch("backend.pro_players.fetch_pro_players_from_api") as mock_fetch:
        mock_fetch.return_value = None  # Return None to skip startup sync

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

        response = client.post("/pro-players/sync")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "ok"
        assert data["count"] == 2
        assert "Stored 2 pro players" in data["message"]


def test_pro_players_endpoint_stores_data(client, sample_pro_players_data, app):
    """Test that /pro-players/sync actually stores data in database."""
    with patch("backend.dota_bet_analyzer.fetch_pro_players_from_api") as mock_fetch:
        mock_fetch.return_value = sample_pro_players_data

        response = client.post("/pro-players/sync")
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


def test_pro_players_endpoint_api_failure(client):
    """Test /pro-players/sync endpoint when OpenDota API fails."""
    with patch("backend.pro_players.requests.get") as mock_get:
        mock_get.side_effect = Exception("Network error")

        response = client.post("/pro-players/sync")

        assert response.status_code == 500
        data = json.loads(response.data)
        assert "error" in data


def test_pro_players_endpoint_empty_response(client):
    """Test /pro-players/sync endpoint with empty array from API."""
    with patch("backend.dota_bet_analyzer.fetch_pro_players_from_api") as mock_fetch:
        mock_fetch.return_value = []

        response = client.post("/pro-players/sync")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "ok"
        assert data["count"] == 0


def test_pro_players_upsert(client, sample_pro_players_data, app):
    """Test that updating existing players works (upsert behavior)."""
    with patch("backend.dota_bet_analyzer.fetch_pro_players_from_api") as mock_fetch:
        mock_fetch.return_value = sample_pro_players_data

        # First insert
        client.post("/pro-players/sync")

        # Update data
        updated_data = sample_pro_players_data.copy()
        updated_data[0]["team_name"] = "Updated Team"
        updated_data[0]["team_tag"] = "UPD"

        mock_fetch.return_value = updated_data

        # Second insert (should update)
        client.post("/pro-players/sync")

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
    from backend.pro_players import fetch_pro_players_from_api

    sample_data = [{"account_id": 123, "name": "test"}]

    with patch("backend.pro_players.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = sample_data
        mock_get.return_value.raise_for_status.return_value = None

        result = fetch_pro_players_from_api()

        assert result == sample_data
        mock_get.assert_called_once_with("https://api.opendota.com/api/proPlayers", timeout=30)


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

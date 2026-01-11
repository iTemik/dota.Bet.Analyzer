"""Tests for d2ba database initialization script."""

import os
import sqlite3
import tempfile

import pytest


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


def test_init_d2ba_db_creates_database(temp_db):
    """Test that init_d2ba_db creates a database file."""
    from scripts.init_d2ba_db import init_d2ba_db

    # Remove temp file first
    os.unlink(temp_db)
    assert not os.path.exists(temp_db)

    # Initialize database
    result = init_d2ba_db(temp_db)

    assert result is True
    assert os.path.exists(temp_db)


def test_init_d2ba_db_creates_pro_players_table(temp_db):
    """Test that pro_players table is created with correct schema."""
    from scripts.init_d2ba_db import init_d2ba_db

    init_d2ba_db(temp_db)

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    # Check table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pro_players'")
    assert cursor.fetchone() is not None

    # Check columns
    cursor.execute("PRAGMA table_info(pro_players)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    expected_columns = {
        "account_id": "INTEGER",
        "steamid": "TEXT",
        "profileurl": "TEXT",
        "personaname": "TEXT",
        "name": "TEXT",
        "fantasy_role": "INTEGER",
        "team_id": "INTEGER",
        "team_name": "TEXT",
        "team_tag": "TEXT",
        "is_pro": "BOOLEAN",
    }

    for col_name, col_type in expected_columns.items():
        assert col_name in columns
        assert columns[col_name] == col_type

    conn.close()


def test_init_d2ba_db_creates_indexes(temp_db):
    """Test that indexes are created correctly."""
    from scripts.init_d2ba_db import init_d2ba_db

    init_d2ba_db(temp_db)

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    # Check indexes exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indexes = {row[0] for row in cursor.fetchall()}

    # Should have indexes on name and team_id
    assert "idx_pro_players_name" in indexes
    assert "idx_pro_players_team_id" in indexes

    conn.close()


def test_init_d2ba_db_primary_key(temp_db):
    """Test that account_id is the primary key."""
    from scripts.init_d2ba_db import init_d2ba_db

    init_d2ba_db(temp_db)

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(pro_players)")
    columns = cursor.fetchall()

    # Find account_id column
    account_id_col = next(col for col in columns if col[1] == "account_id")
    # Column format: (cid, name, type, notnull, dflt_value, pk)
    assert account_id_col[5] == 1  # pk field should be 1

    conn.close()


def test_init_d2ba_db_idempotent(temp_db):
    """Test that running init_d2ba_db multiple times is safe."""
    from scripts.init_d2ba_db import init_d2ba_db

    # Run twice
    result1 = init_d2ba_db(temp_db)
    result2 = init_d2ba_db(temp_db)

    assert result1 is True
    assert result2 is True

    # Verify database still works
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pro_players'")
    assert cursor.fetchone() is not None
    conn.close()

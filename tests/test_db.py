"""Tests for backend/db.py: the two SQLite connections."""

import sqlite3

import pytest

from backend.db import CACHE_DB_FILENAME, USER_DB_FILENAME, get_cache_db, get_user_db
from scripts.migrate import DATABASES


def test_filenames_match_migration_runner() -> None:
    """The app opens the same files the migration runner creates (instance/<DATABASES key>.sqlite)."""
    assert {f"{name}.sqlite" for name in DATABASES} == {CACHE_DB_FILENAME, USER_DB_FILENAME}


def test_connections_open_migrated_files_once_per_context(app) -> None:
    """Each getter returns one connection per app context to the migrated file, closed on teardown."""
    with app.app_context():
        cache, user = get_cache_db(), get_user_db()
        assert get_cache_db() is cache and get_user_db() is user
        assert cache.execute("SELECT name FROM sqlite_master WHERE name = 'teams'").fetchone() is not None
        assert user.execute("SELECT name FROM sqlite_master WHERE name = 'predictions'").fetchone() is not None
        assert user.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert isinstance(cache.execute("SELECT 1 AS one").fetchone(), sqlite3.Row)
    with pytest.raises(sqlite3.ProgrammingError):
        cache.execute("SELECT 1")

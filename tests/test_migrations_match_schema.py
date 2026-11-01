"""Check that the documented schema files match what the migrations build.

d2ba_schema.sql and predictions_schema.sql are documentation only (nothing applies them), so this test
runs all migrations on an empty file and compares tables, columns, indexes and foreign keys with the schema file.
"""

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from scripts.migrate import MigrationRunner

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"

# Tables SQLite or the migration runner create on their own; schema files do not document them
INTERNAL_TABLES = {"migration_history", "sqlite_sequence"}


def describe_schema(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Describe every user table of a database.

    Args:
        conn: Open SQLite connection

    Returns:
        Table name → {"columns": [(name, type, notnull, default, pk)], "indexes": {name: (unique, columns)},
        "foreign_keys": [(column, table, to_column)]}; columns keep their order
    """
    tables = [
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
        if row[0] not in INTERNAL_TABLES
    ]
    schema: dict[str, dict[str, Any]] = {}
    for table in tables:
        columns = [
            (name, col_type.upper(), notnull, default, pk)
            for _cid, name, col_type, notnull, default, pk in conn.execute(f"PRAGMA table_info({table})")
        ]
        indexes = {
            name: (unique, tuple(col[2] for col in conn.execute(f"PRAGMA index_info({name})")))
            for _seq, name, unique, _origin, _partial in conn.execute(f"PRAGMA index_list({table})")
        }
        foreign_keys = sorted((row[3], row[2], row[4]) for row in conn.execute(f"PRAGMA foreign_key_list({table})"))
        schema[table] = {"columns": columns, "indexes": indexes, "foreign_keys": foreign_keys}
    return schema


@pytest.mark.parametrize(
    ("database", "schema_file"),
    [("d2ba", "d2ba_schema.sql"), ("predictions", "predictions_schema.sql")],
)
def test_migrations_match_schema_file(tmp_path: Path, database: str, schema_file: str) -> None:
    """All migrations on an empty database build exactly the tables the schema file documents."""
    migrated_path = tmp_path / f"{database}.sqlite"
    assert MigrationRunner(db_path=str(migrated_path), database=database).run_all_pending()

    with sqlite3.connect(migrated_path) as migrated, sqlite3.connect(":memory:") as documented:
        documented.executescript((BACKEND_DIR / schema_file).read_text(encoding="utf-8"))
        migrated_schema = describe_schema(migrated)
        documented_schema = describe_schema(documented)

    assert sorted(documented_schema) == sorted(migrated_schema), f"{schema_file}: tables differ from migrations"
    for table, migrated_table in migrated_schema.items():
        assert documented_schema[table] == migrated_table, f"{schema_file}: table {table} differs from migrations"


def test_describe_schema_sees_a_missing_column() -> None:
    """The comparison notices a column added by a migration but missing from the schema file."""
    with sqlite3.connect(":memory:") as old, sqlite3.connect(":memory:") as new:
        old.execute("CREATE TABLE t (a INTEGER PRIMARY KEY)")
        new.execute("CREATE TABLE t (a INTEGER PRIMARY KEY)")
        new.execute("ALTER TABLE t ADD COLUMN b TEXT")

        assert describe_schema(old) != describe_schema(new)


def test_describe_schema_skips_internal_tables() -> None:
    """The runner's migration_history and SQLite's sqlite_sequence are not part of the comparison."""
    with sqlite3.connect(":memory:") as conn:
        conn.execute("CREATE TABLE migration_history (id INTEGER PRIMARY KEY AUTOINCREMENT)")
        conn.execute("INSERT INTO migration_history DEFAULT VALUES")

        assert describe_schema(conn) == {}

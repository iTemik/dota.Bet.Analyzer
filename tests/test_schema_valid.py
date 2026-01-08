import sqlite3
from pathlib import Path

import pytest

SQL_PATH = Path("backend/schema.sql")


@pytest.fixture(scope="module")
def conn():
    sql = SQL_PATH.read_text()
    con = sqlite3.connect(":memory:")
    try:
        con.executescript(sql)
        yield con
    finally:
        con.close()


def table_info(con, table):
    cur = con.execute(f"PRAGMA table_info('{table}')")
    return list(cur.fetchall())


def index_list(con):
    cur = con.execute("SELECT name FROM sqlite_master WHERE type='index'")
    return {row[0] for row in cur.fetchall()}


def test_schema_executes(conn):
    # If the script runs without raising, it's valid SQL for SQLite
    assert conn is not None


def test_inferred_primary_keys(conn):
    # Check some inferred primary keys
    info = table_info(conn, "heroes")
    # columns are (cid,name,type,notnull,dflt_value,pk)
    hero_pk = next((c for c in info if c[1] == "id"), None)
    assert hero_pk is not None and hero_pk[5] == 1

    item_pk = next((c for c in table_info(conn, "items") if c[1] == "id"), None)
    assert item_pk is not None and item_pk[5] == 1

    queue_pk = next((c for c in table_info(conn, "queue") if c[1] == "id"), None)
    assert queue_pk is not None and queue_pk[5] == 1

    teams_pk = next((c for c in table_info(conn, "teams") if c[1] == "team_id"), None)
    assert teams_pk is not None and teams_pk[5] == 1

    webhooks_pk = next((c for c in table_info(conn, "webhooks") if c[1] == "hook_id"), None)
    assert webhooks_pk is not None and webhooks_pk[5] == 1


def test_timestamp_columns_are_integer(conn):
    matches_info = table_info(conn, "matches")
    start_time = next(c for c in matches_info if c[1] == "start_time")
    assert start_time[2].upper() == "INTEGER"

    players_info = table_info(conn, "players")
    last_login = next(c for c in players_info if c[1] == "last_login")
    assert last_login[2].upper() == "INTEGER"

    api_usage_info = table_info(conn, "api_key_usage")
    timestamp = next(c for c in api_usage_info if c[1] == "timestamp")
    assert timestamp[2].upper() == "INTEGER"


def test_indices_exist(conn):
    idxs = index_list(conn)
    assert "idx_matches_match_id" in idxs
    assert "idx_player_matches_account_id" in idxs
    assert "idx_webhooks_hook_id" in idxs
    assert "idx_player_match_history_player_slot" in idxs

"""Tests for the teams list sync: POST/GET /api/teams/sync, the 30-day check and the background startup sync."""

import time
from unittest.mock import patch

import pytest

from backend import teams_sync
from backend.pro_players import get_d2ba_db
from backend.teams_sync import (
    TEAMS_MAX_AGE_SECONDS,
    TeamsSyncRunningError,
    get_teams_synced_at,
    is_teams_sync_due,
    run_teams_sync,
    sync_teams_on_startup,
)

TEAMS = [
    {"team_id": 1, "rating": 1500.0, "name": "Team A", "tag": "TA", "logo_url": None, "last_match_time": 100},
    {"team_id": 2, "rating": 1400.0, "name": "Team B", "tag": "TB", "logo_url": None, "last_match_time": 200},
]


@pytest.fixture
def mock_fetch():
    """OpenDota /teams pages, no real request."""
    with patch("backend.teams_sync.fetch_teams_from_api", return_value=TEAMS) as mock:
        yield mock


def set_synced_at(app, synced_at: int) -> None:
    """Record a past teams sync."""
    with app.app_context():
        db = get_d2ba_db()
        db.execute("INSERT INTO sync_state (name, synced_at) VALUES ('teams', ?)", (synced_at,))
        db.commit()


def test_run_stores_teams_and_records_time(app, mock_fetch):
    with app.app_context():
        before = int(time.time())
        assert run_teams_sync() == 2
        assert get_d2ba_db().execute("SELECT COUNT(*) FROM teams").fetchone()[0] == 2
        assert get_teams_synced_at() >= before


def test_run_without_teams_keeps_no_sync_time(app):
    with app.app_context(), patch("backend.teams_sync.fetch_teams_from_api", return_value=[]):
        assert run_teams_sync() == 0
        assert get_teams_synced_at() is None


def test_run_refuses_a_second_concurrent_sync(app, mock_fetch):
    with app.app_context(), teams_sync._sync_lock:
        with pytest.raises(TeamsSyncRunningError):
            run_teams_sync()
    mock_fetch.assert_not_called()


def test_due_when_never_synced_or_30_days_old(app):
    now = time.time()
    with app.app_context():
        assert is_teams_sync_due(now)
    set_synced_at(app, int(now) - TEAMS_MAX_AGE_SECONDS + 3600)
    with app.app_context():
        assert not is_teams_sync_due(now)
        assert is_teams_sync_due(now + 3600)


def test_status_endpoint(app, client, mock_fetch):
    assert client.get("/api/teams/sync").get_json() == {"synced_at": None, "running": False}
    client.post("/api/teams/sync")
    data = client.get("/api/teams/sync").get_json()
    assert data["running"] is False
    assert isinstance(data["synced_at"], int)


def test_status_endpoint_running(client):
    with teams_sync._sync_lock:
        assert client.get("/api/teams/sync").get_json()["running"] is True


def test_sync_endpoint_returns_count_and_time(client, mock_fetch):
    rv = client.post("/api/teams/sync")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["synced_count"] == 2
    assert data["message"] == "Stored 2 teams"
    assert isinstance(data["synced_at"], int)


def test_sync_endpoint_no_teams(client):
    with patch("backend.teams_sync.fetch_teams_from_api", return_value=[]):
        rv = client.post("/api/teams/sync")
    assert rv.status_code == 200
    assert rv.get_json() == {"synced_count": 0, "message": "No teams data available", "synced_at": None}


def test_sync_endpoint_conflict_while_running(client, mock_fetch):
    with teams_sync._sync_lock:
        rv = client.post("/api/teams/sync")
    assert rv.status_code == 409
    assert rv.get_json()["code"] == "TEAMS_SYNC_RUNNING"


def test_sync_endpoint_database_error(client, mock_fetch):
    with patch("backend.teams_sync.store_teams", side_effect=RuntimeError("disk full")):
        rv = client.post("/api/teams/sync")
    assert rv.status_code == 500
    assert rv.get_json()["code"] == "FAILED_TO_STORE_TEAMS"


def test_startup_syncs_in_background_when_due(app, mock_fetch):
    thread = sync_teams_on_startup(app)
    assert thread is not None
    thread.join(timeout=5)
    with app.app_context():
        assert get_teams_synced_at() is not None
        assert get_d2ba_db().execute("SELECT COUNT(*) FROM teams").fetchone()[0] == 2


def test_startup_makes_no_request_when_recent(app, mock_fetch):
    set_synced_at(app, int(time.time()) - 24 * 3600)
    assert sync_teams_on_startup(app) is None
    mock_fetch.assert_not_called()


def test_startup_skips_debug_reloader_parent(app, mock_fetch, monkeypatch):
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
    app.debug = True
    assert sync_teams_on_startup(app) is None
    mock_fetch.assert_not_called()


def test_startup_errors_are_logged_not_raised(app):
    with patch("backend.teams_sync.fetch_teams_from_api", side_effect=ConnectionError("down")):
        thread = sync_teams_on_startup(app)
        thread.join(timeout=5)
    with app.app_context():
        assert get_teams_synced_at() is None

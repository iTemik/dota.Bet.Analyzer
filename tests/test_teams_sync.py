"""Tests for the teams list sync: POST /api/teams/sync, full vs incremental, the 24-hour check and automatic syncs."""

import time
from unittest.mock import patch

import pytest

from backend import teams_sync
from backend.opendota import OpenDotaError
from backend.pro_players import get_d2ba_db, store_teams
from backend.teams_sync import (
    RETRY_AFTER_FAILURE_SECONDS,
    TEAMS_MAX_AGE_SECONDS,
    TeamsSyncRunningError,
    fetch_recent_teams,
    get_teams_synced_at,
    is_teams_sync_due,
    run_teams_sync,
    sync_teams_if_obsolete,
    sync_teams_on_startup,
)

TEAMS = [
    {"team_id": 1, "rating": 1500.0, "name": "Team A", "tag": "TA", "logo_url": None, "last_match_time": 100},
    {"team_id": 2, "rating": 1400.0, "name": "Team B", "tag": "TB", "logo_url": None, "last_match_time": 200},
]


@pytest.fixture(autouse=True)
def reset_failure():
    """No failed automatic sync from another test."""
    teams_sync._last_failure = None
    yield
    teams_sync._last_failure = None


@pytest.fixture
def mock_fetch():
    """OpenDota /teams pages, no real request."""
    with patch("backend.teams_sync.fetch_teams_from_api", return_value=TEAMS) as mock:
        yield mock


def explorer_answer(url, params=None, timeout=30):
    """Explorer answers: team 2 played again, team 3 is new, team 4 has no name row."""
    sql = params["sql"]
    if "FROM team_rating" in sql:
        return {
            "rows": [
                {"team_id": 2, "rating": 1450.0, "last_match_time": 300},
                {"team_id": 3, "rating": 1000.0, "last_match_time": 250},
                {"team_id": 4, "rating": 990.0, "last_match_time": 260},
            ]
        }
    return {
        "rows": [
            {"team_id": 2, "name": "Team B2", "tag": "TB", "logo_url": None},
            {"team_id": 3, "name": "Team C", "tag": "TC", "logo_url": "c.png"},
        ]
    }


@pytest.fixture
def mock_explorer():
    with patch("backend.teams_sync.get_json", side_effect=explorer_answer) as mock:
        yield mock


def store_known_teams(app) -> None:
    with app.app_context():
        store_teams(TEAMS)


def set_synced_at(app, synced_at: int) -> None:
    """Record a past teams sync."""
    with app.app_context():
        db = get_d2ba_db()
        db.execute("INSERT INTO sync_state (name, synced_at) VALUES ('teams', ?)", (synced_at,))
        db.commit()


def team_names(app) -> dict[int, str]:
    with app.app_context():
        return {row[0]: row[1] for row in get_d2ba_db().execute("SELECT team_id, name FROM teams")}


def test_run_with_empty_table_is_full_and_records_time(app, mock_fetch, mock_explorer):
    with app.app_context():
        before = int(time.time())
        assert run_teams_sync() == 2
        assert get_teams_synced_at() >= before
    assert team_names(app) == {1: "Team A", 2: "Team B"}
    mock_explorer.assert_not_called()


def test_full_run_without_teams_keeps_no_sync_time(app):
    with app.app_context(), patch("backend.teams_sync.fetch_teams_from_api", return_value=[]):
        assert run_teams_sync() == 0
        assert get_teams_synced_at() is None


def test_run_with_stored_teams_is_incremental(app, mock_fetch, mock_explorer):
    store_known_teams(app)
    with app.app_context():
        assert run_teams_sync() == 2
        assert get_teams_synced_at() is not None
    mock_fetch.assert_not_called()
    assert mock_explorer.call_count == 2
    assert "last_match_time >= 200" in mock_explorer.call_args_list[0].kwargs["params"]["sql"]
    assert "team_id IN (2,3,4)" in mock_explorer.call_args_list[1].kwargs["params"]["sql"]
    assert team_names(app) == {1: "Team A", 2: "Team B2", 3: "Team C"}
    with app.app_context():
        row = get_d2ba_db().execute("SELECT rating, last_match_time FROM teams WHERE team_id = 2").fetchone()
    assert tuple(row) == (1450.0, 300)


def test_incremental_run_without_new_games_records_time(app):
    store_known_teams(app)
    with app.app_context(), patch("backend.teams_sync.get_json", return_value={"rows": []}) as mock:
        assert run_teams_sync() == 0
        assert get_teams_synced_at() is not None
    assert mock.call_count == 1


def test_full_flag_fetches_every_page(app, mock_fetch, mock_explorer):
    store_known_teams(app)
    with app.app_context():
        assert run_teams_sync(full=True) == 2
    mock_fetch.assert_called_once()
    mock_explorer.assert_not_called()


def test_recent_teams_batches_ids(app):
    ratings = {"rows": [{"team_id": i, "rating": 1000.0, "last_match_time": 5} for i in range(450)]}
    with patch("backend.teams_sync.get_json", side_effect=[ratings, {"rows": []}, {"rows": []}, {"rows": []}]) as m:
        assert fetch_recent_teams(5) == []
    assert m.call_count == 4  # 1 rating query + 200 + 200 + 50 ids


def test_recent_teams_errors(app):
    with patch("backend.teams_sync.get_json", side_effect=OpenDotaError(503, "NETWORK_ERROR", "down")):
        with pytest.raises(ConnectionError):
            fetch_recent_teams(0)
    with patch("backend.teams_sync.get_json", return_value={"rows": None, "err": "syntax error"}):
        with pytest.raises(ValueError, match="syntax error"):
            fetch_recent_teams(0)


def test_run_refuses_a_second_concurrent_sync(app, mock_fetch):
    with app.app_context(), teams_sync._sync_lock:
        with pytest.raises(TeamsSyncRunningError):
            run_teams_sync()
    mock_fetch.assert_not_called()


def test_due_when_never_synced_or_24_hours_old(app):
    now = time.time()
    with app.app_context():
        assert is_teams_sync_due(now)
    set_synced_at(app, int(now) - TEAMS_MAX_AGE_SECONDS + 3600)
    with app.app_context():
        assert not is_teams_sync_due(now)
        assert is_teams_sync_due(now + 3600)


def test_sync_endpoint_returns_count_and_time(client, mock_fetch):
    rv = client.post("/api/teams/sync")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["synced_count"] == 2
    assert data["message"] == "Stored 2 teams"
    assert isinstance(data["synced_at"], int)


def test_sync_endpoint_full_flag(app, client, mock_fetch, mock_explorer):
    store_known_teams(app)
    assert client.post("/api/teams/sync?full=true").status_code == 200
    mock_fetch.assert_called_once()
    mock_explorer.assert_not_called()


def test_sync_endpoint_no_teams(client):
    with patch("backend.teams_sync.fetch_teams_from_api", return_value=[]):
        rv = client.post("/api/teams/sync")
    assert rv.status_code == 200
    assert rv.get_json() == {"synced_count": 0, "message": "No new teams data", "synced_at": None}


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


def test_obsolete_data_syncs_in_background(app, mock_fetch):
    thread = sync_teams_if_obsolete(app)
    assert thread is not None
    thread.join(timeout=5)
    with app.app_context():
        assert get_teams_synced_at() is not None
    assert team_names(app) == {1: "Team A", 2: "Team B"}


def test_recent_data_makes_no_request(app, mock_fetch):
    set_synced_at(app, int(time.time()) - 3600)
    assert sync_teams_if_obsolete(app) is None
    mock_fetch.assert_not_called()


def test_no_automatic_sync_while_one_runs(app, mock_fetch):
    with teams_sync._sync_lock:
        assert sync_teams_if_obsolete(app) is None
    mock_fetch.assert_not_called()


def test_failed_automatic_sync_is_logged_and_waits_before_retry(app):
    with patch("backend.teams_sync.fetch_teams_from_api", side_effect=ConnectionError("down")) as mock:
        sync_teams_if_obsolete(app).join(timeout=5)
        assert sync_teams_if_obsolete(app) is None
        teams_sync._last_failure = time.time() - RETRY_AFTER_FAILURE_SECONDS
        sync_teams_if_obsolete(app).join(timeout=5)
    assert mock.call_count == 2
    with app.app_context():
        assert get_teams_synced_at() is None


def test_startup_syncs_when_obsolete(app, mock_fetch):
    thread = sync_teams_on_startup(app)
    assert thread is not None
    thread.join(timeout=5)
    mock_fetch.assert_called_once()


def test_startup_skips_debug_reloader_parent(app, mock_fetch, monkeypatch):
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
    app.debug = True
    assert sync_teams_on_startup(app) is None
    mock_fetch.assert_not_called()


@pytest.mark.parametrize("url", ["/api/teams/search?q=Team", "/api/matches"])
def test_requests_start_sync_when_obsolete(app, client, url):
    app.config["TESTING"] = False
    try:
        with (
            patch("backend.dota_bet_analyzer.sync_teams_if_obsolete") as mock_sync,
            patch("backend.dota_bet_analyzer.get_matches", return_value={"upcoming": [], "finished": []}),
        ):
            client.get(url)
    finally:
        app.config["TESTING"] = True
    mock_sync.assert_called_once()


def test_requests_in_tests_never_sync(client):
    with patch("backend.dota_bet_analyzer.sync_teams_if_obsolete") as mock_sync:
        client.get("/api/teams/search?q=Team")
    mock_sync.assert_not_called()

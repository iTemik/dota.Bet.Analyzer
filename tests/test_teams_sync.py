"""Tests for the teams list sync: full vs incremental, and queueing the teams job on requests."""

import time
from unittest.mock import patch

import pytest

from backend.db import get_cache_db
from backend.jobs import get_synced_at
from backend.opendota import OpenDotaError
from backend.pro_players import store_teams
from backend.teams_sync import fetch_recent_teams, run_teams_sync

TEAMS = [
    {"team_id": 1, "rating": 1500.0, "name": "Team A", "tag": "TA", "logo_url": None, "last_match_time": 100},
    {"team_id": 2, "rating": 1400.0, "name": "Team B", "tag": "TB", "logo_url": None, "last_match_time": 200},
]


@pytest.fixture
def mock_fetch():
    """OpenDota /teams pages, no real request."""
    with patch("backend.teams_sync.fetch_teams_from_api", return_value=TEAMS) as mock:
        yield mock


def explorer_answer(url, params=None, timeout=30, background=False):
    """Explorer answers: team 2 played again, team 3 is new, team 4 has no name row."""
    assert background, "teams sync requests are background requests"
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


def team_names(app) -> dict[int, str]:
    with app.app_context():
        return {row[0]: row[1] for row in get_cache_db().execute("SELECT team_id, name FROM teams")}


def test_run_with_empty_table_is_full_and_records_time(app, mock_fetch, mock_explorer):
    with app.app_context():
        before = int(time.time())
        assert run_teams_sync() == 2
        assert get_synced_at("teams") >= before
    assert team_names(app) == {1: "Team A", 2: "Team B"}
    mock_explorer.assert_not_called()


def test_full_run_without_teams_keeps_no_sync_time(app):
    with app.app_context(), patch("backend.teams_sync.fetch_teams_from_api", return_value=[]):
        assert run_teams_sync() == 0
        assert get_synced_at("teams") is None


def test_run_with_stored_teams_is_incremental(app, mock_fetch, mock_explorer):
    store_known_teams(app)
    with app.app_context():
        assert run_teams_sync() == 2
        assert get_synced_at("teams") is not None
    mock_fetch.assert_not_called()
    assert mock_explorer.call_count == 2
    assert "last_match_time >= 200" in mock_explorer.call_args_list[0].kwargs["params"]["sql"]
    assert "team_id IN (2,3,4)" in mock_explorer.call_args_list[1].kwargs["params"]["sql"]
    assert team_names(app) == {1: "Team A", 2: "Team B2", 3: "Team C"}
    with app.app_context():
        row = get_cache_db().execute("SELECT rating, last_match_time FROM teams WHERE team_id = 2").fetchone()
    assert tuple(row) == (1450.0, 300)


def test_incremental_run_without_new_games_records_time(app):
    store_known_teams(app)
    with app.app_context(), patch("backend.teams_sync.get_json", return_value={"rows": []}) as mock:
        assert run_teams_sync() == 0
        assert get_synced_at("teams") is not None
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


@pytest.mark.parametrize("url", ["/api/teams/search?q=Team", "/api/matches"])
def test_requests_queue_teams_job_when_due(app, client, url):
    app.config["TESTING"] = False
    try:
        with (
            patch("backend.routes.catalog.queue_job_if_due") as mock_sync,
            patch("backend.routes.catalog.get_matches", return_value={"upcoming": [], "finished": []}),
        ):
            client.get(url)
    finally:
        app.config["TESTING"] = True
    mock_sync.assert_called_once_with("teams")


def test_requests_in_tests_never_queue_jobs(client):
    with patch("backend.routes.catalog.queue_job_if_due") as mock_sync:
        client.get("/api/teams/search?q=Team")
    mock_sync.assert_not_called()

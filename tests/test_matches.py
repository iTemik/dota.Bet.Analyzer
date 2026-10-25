"""Tests for the Liquipedia matches list (backend.matches) and GET /api/matches."""

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest
import requests

from backend.matches import CACHE_KEY, ERROR_CACHE_TTL, parse_matches

NOW = 1_800_000_000


def team(name: str, short: str) -> str:
    """Liquipedia team template: the link title is the full team name."""
    return (
        '<span class="team-template-team-short"><span class="team-template-image-icon"><img src="/x.png"></span>'
        f'<span class="team-template-text"><a href="/dota2/{name}" title="{name}">{short}</a></span></span>'
    )


def ticker(team1: str, team2: str, start: int, versus: str, finished: bool = False) -> str:
    """One series in the classic match ticker markup."""
    done = ' data-finished="finished"' if finished else ""
    return (
        '<table class="wikitable wikitable-striped infobox_matches_content"><tr>'
        f'<td class="team-left">{team1}</td>'
        f'<td class="versus"><div>{versus}</div></td>'
        f'<td class="team-right">{team2}</td></tr>'
        f'<tr><td class="match-filler"><span class="timer-object" data-timestamp="{start}"{done}>date</span>'
        '<a title="Some League">Some League</a></td></tr></table>'
    )


def match_info(team1: str, team2: str, start: int, score: str, best_of: str, finished: bool = False) -> str:
    """One series in the newer match-info markup."""
    done = ' data-finished="finished"' if finished else ""
    return (
        '<div class="match-info"><div class="match-info-top-row">'
        f'<span class="timer-object" data-timestamp="{start}"{done}>date</span></div>'
        '<div class="match-info-header">'
        f'<div class="match-info-header-opponent match-info-header-opponent-left">{team1}</div>'
        '<div class="match-info-header-scoreholder">'
        f'<span class="match-info-header-scoreholder-upper">{score}</span>'
        f'<span class="match-info-header-scoreholder-lower">({best_of})</span></div>'
        f'<div class="match-info-header-opponent">{team2}</div></div></div>'
    )


PAGE = "".join(
    [
        ticker(
            team("Team Alpha", "Alpha"),
            team("Beta Squad", "BETA"),
            NOW + 7200,
            'vs<br><abbr title="Best of 3">Bo3</abbr>',
        ),
        ticker(
            team("Gamma", "GAM"), team("Team Alpha", "Alpha"), NOW + 3600, 'vs<br><abbr title="Best of 5">Bo5</abbr>'
        ),
        ticker(team("Gamma", "GAM"), team("Delta", "DEL"), NOW - 600, '1:0<br><abbr title="Best of 3">Bo3</abbr>'),
        ticker(team("Beta Squad", "BETA"), team("Delta", "DEL"), NOW - 9000, "2:1 <abbr>Bo3</abbr>", finished=True),
        match_info(team("Gamma", "GAM"), team("Team Alpha", "Alpha"), NOW - 20000, "0:2", "Bo3", finished=True),
        # Same series repeated in another list on the page
        match_info(team("Gamma", "GAM"), team("Team Alpha", "Alpha"), NOW - 20000, "0:2", "Bo3", finished=True),
        '<div class="match-info"><span class="timer-object" data-timestamp="1">x</span></div>',
    ]
)


def test_parse_matches_reads_both_markups():
    matches = parse_matches(PAGE)

    assert matches == [
        {"start_time": NOW + 7200, "best_of": 3, "team1": "Team Alpha", "team2": "Beta Squad", "finished": False,
         "score1": None, "score2": None},
        {"start_time": NOW + 3600, "best_of": 5, "team1": "Gamma", "team2": "Team Alpha", "finished": False,
         "score1": None, "score2": None},
        {"start_time": NOW - 600, "best_of": 3, "team1": "Gamma", "team2": "Delta", "finished": False,
         "score1": 1, "score2": 0},
        {"start_time": NOW - 9000, "best_of": 3, "team1": "Beta Squad", "team2": "Delta", "finished": True,
         "score1": 2, "score2": 1},
        {"start_time": NOW - 20000, "best_of": 3, "team1": "Gamma", "team2": "Team Alpha", "finished": True,
         "score1": 0, "score2": 2},
    ]  # fmt: skip


def test_parse_matches_tbd_team_without_link():
    page = ticker(team("Gamma", "GAM"), '<span class="team-template-text">TBD</span>', NOW + 60, "vs Bo1")

    assert parse_matches(page)[0]["team2"] == "TBD"


class FakeRedis:
    """In-memory stand-in for the Redis client (get/setex)."""

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str):
        return self.store.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value.encode()
        self.ttls[key] = ttl


@pytest.fixture
def fake_redis():
    redis = FakeRedis()
    with patch("backend.matches.redis_client", redis):
        yield redis


@pytest.fixture
def known_teams(app):
    """Teams table rows the Liquipedia names are matched against."""
    db = sqlite3.connect(f"{app.instance_path}/d2ba.sqlite")
    db.executemany(
        "INSERT INTO teams (team_id, name, tag, logo_url, last_match_time) VALUES (?, ?, ?, ?, ?)",
        [
            (11, "Team Alpha", "Alpha", "https://logo/alpha.png", 100),
            (22, "Beta Squad", "BETA", None, 100),
            (33, "Gamma", "GAM", "https://logo/gamma.png", 50),
            (34, "Gamma Old", "GAM", "https://logo/gamma-old.png", 10),
        ],
    )
    db.commit()
    db.close()


def liquipedia_response(html: str, status: int = 200) -> MagicMock:
    response = MagicMock(status_code=status)
    response.json.return_value = {"parse": {"title": "Liquipedia:Matches", "text": html}}
    return response


def get_matches(client, response):
    with (
        patch("backend.matches.requests.get", return_value=response) as get,
        patch("backend.matches.time.time", return_value=NOW),
    ):
        return client.get("/api/matches"), get


def test_lists_upcoming_and_finished(client, fake_redis, known_teams):
    response, get = get_matches(client, liquipedia_response(PAGE))

    assert response.status_code == 200
    alpha = {"name": "Team Alpha", "team_id": 11, "logo_url": "https://logo/alpha.png"}
    beta = {"name": "Beta Squad", "team_id": 22, "logo_url": None}
    gamma = {"name": "Gamma", "team_id": 33, "logo_url": "https://logo/gamma.png"}
    delta = {"name": "Delta", "team_id": None, "logo_url": None}
    assert response.get_json() == {
        "upcoming": [
            {"start_time": NOW + 3600, "best_of": 5, "team1": gamma, "team2": alpha},
            {"start_time": NOW + 7200, "best_of": 3, "team1": alpha, "team2": beta},
        ],
        "finished": [
            {"start_time": NOW - 9000, "best_of": 3, "team1": beta, "team2": delta, "score1": 2, "score2": 1},
            {"start_time": NOW - 20000, "best_of": 3, "team1": gamma, "team2": alpha, "score1": 0, "score2": 2},
        ],
    }
    assert get.call_count == 1
    assert get.call_args.kwargs["params"]["page"] == "Liquipedia:Matches"
    assert get.call_args.kwargs["headers"]["User-Agent"].startswith("DotaBetAnalyzer/")


def test_second_call_uses_cache(client, fake_redis, known_teams):
    get_matches(client, liquipedia_response(PAGE))
    response, get = get_matches(client, liquipedia_response(""))

    assert len(response.get_json()["upcoming"]) == 2
    assert get.call_count == 0


def test_liquipedia_error_returns_503_and_is_cached(client, fake_redis):
    response, _ = get_matches(client, liquipedia_response("", status=429))

    assert response.status_code == 503
    assert response.get_json()["code"] == "FAILED_TO_FETCH_MATCHES"
    assert fake_redis.ttls[CACHE_KEY] == ERROR_CACHE_TTL

    response, get = get_matches(client, liquipedia_response(PAGE))
    assert response.status_code == 503
    assert get.call_count == 0


def test_network_error_returns_503(client, fake_redis):
    with patch("backend.matches.requests.get", side_effect=requests.ConnectionError("down")):
        response = client.get("/api/matches")

    assert response.status_code == 503


def test_unexpected_answer_returns_503(client, fake_redis):
    response = MagicMock(status_code=200)
    response.json.return_value = {"error": {"code": "missingtitle"}}

    response, _ = get_matches(client, response)

    assert response.status_code == 503
    assert json.loads(fake_redis.store[CACHE_KEY])["error"]


def test_works_without_redis(client, known_teams):
    broken = MagicMock()
    broken.get.side_effect = ConnectionError("no redis")
    broken.setex.side_effect = ConnectionError("no redis")
    with patch("backend.matches.redis_client", broken):
        response, get = get_matches(client, liquipedia_response(PAGE))

    assert response.status_code == 200
    assert get.call_count == 1

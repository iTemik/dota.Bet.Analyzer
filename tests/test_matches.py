"""Tests for the Liquipedia matches list (backend.matches) and GET /api/matches."""

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest
import requests

from backend.matches import (
    CACHE_KEY,
    ERROR_CACHE_TTL,
    TeamMatcher,
    normalize_team_name,
    parse_matches,
)

NOW = 1_800_000_000


def team(name: str, short: str, page: bool = True, dark_icon: bool = False) -> str:
    """Liquipedia team block: the name link title is the full name; a team without a wiki page has a redlink."""
    title = name if page else f"{name} (page does not exist)"
    icons = (
        f'<span class="team-template-image-icon"><a title="{title}"><img alt="" src="/img/{short}.png" /></a></span>'
    )
    if dark_icon:
        icons = (
            f'<span class="team-template-lightmode"><img src="/img/{short}-light.png" /></span>'
            f'<span class="team-template-darkmode"><img src="/img/{short}-dark.png" /></span>'
        )
    return (
        f'<div class="block-team">{icons}<span class="name"><a href="/dota2/x" title="{title}">{short}</a></span></div>'
    )


TBD = (
    '<div class="block-team"><span class="team-template-image-icon"><i class="far fa-users"></i></span>'
    '<span class="name">TBD</span></div>'
)


def score_spans(score: str) -> str:
    """Scoreholder upper part: "vs" for an upcoming series, else score spans like Liquipedia's."""
    if score == "vs":
        return "vs"
    left, right = score.split(":")
    return (
        f'<span class="match-info-header-scoreholder-score">{left}</span>'
        '<span class="match-info-header-scoreholder-divider">:</span>'
        f'<span class="match-info-header-scoreholder-score">{right}</span>'
    )


LEAGUE = "Some League 2:3 Bo5 Cup"
LEAGUE_URL = "https://liquipedia.net/dota2/Some_League/Cup"


def tournament_block(name: str) -> str:
    """Tournament line under a series: light and dark icons, then the name link (trimmed real markup)."""
    icons = "".join(
        f'<span class="league-icon-small-image {mode}"><a href="/dota2/Some_League/Cup#Day" title="Some League/Cup">'
        f'<img alt="" src="/img/league-{mode}.png" /></a></span>'
        for mode in ("lightmode", "darkmode")
    )
    return (
        f'<div class="match-info-tournament"><span>{icons}</span><span class="match-info-tournament-wrapper">'
        '<span class="match-info-tournament-name"><a href="/dota2/Some_League/Cup#Day" title="Some League/Cup">'
        f"<span>{name}</span></a></span></span></div>"
    )


def match_info(
    team1: str,
    team2: str,
    start: int,
    score: str,
    best_of: str = "(Bo3)",
    finished: bool = False,
    tournament: str = f"{LEAGUE} - October 26",
) -> str:
    """One series of the Liquipedia match ticker (trimmed real markup); an empty tournament leaves its line out."""
    done = ' data-finished="finished"' if finished else ""
    return (
        '<div class="match-info"><span class="match-info-countdown">'
        f'<span class="timer-object" data-format="full" data-timestamp="{start}"{done}>October 26, 2026 - 12:00 '
        '<abbr title="Singapore Time (UTC+8)">SGT</abbr></span></span><div class="match-info-header">'
        f'<div class="match-info-header-opponent match-info-header-opponent-left">{team1}</div>'
        '<div class="match-info-header-scoreholder"><span class="match-info-header-scoreholder-scorewrapper">'
        f'<span class="match-info-header-scoreholder-upper">{score_spans(score)}</span>'
        f'<span class="match-info-header-scoreholder-lower">{best_of}</span></span></div>'
        f'<div class="match-info-header-opponent">{team2}</div></div>'
        f"{tournament_block(tournament) if tournament else ''}</div>"
    )


PAGE = (
    # Upcoming tab
    '<div data-filter-expansion-template="type=upcoming"><div class="">'
    + match_info(team("Team Alpha", "Alpha"), team("Beta Squad", "BETA", page=False), NOW + 7200, "vs")
    + match_info(team("Gamma", "GAM", dark_icon=True), team("Team Alpha", "Alpha"), NOW + 3600, "vs", "(Bo5)")
    + match_info(TBD, TBD, NOW + 9000, "vs", "", tournament="")
    + '</div></div><div class="toggle-area-content-inactive" data-toggle-area-content="2">'
    # Recent tab
    + match_info(team("Beta Squad", "BETA"), team("Delta", "DEL"), NOW - 9000, "2:1", finished=True)
    + match_info(team("Gamma", "GAM"), team("Team Alpha", "Alpha"), NOW - 20000, "0:2", finished=True)
    + match_info(team("Delta", "DEL"), team("Gamma", "GAM"), NOW - 30000, "FF:W", "", True, f"{LEAGUE} - Playoffs")
    + '<div class="match-info"><span class="timer-object" data-timestamp="1">x</span></div></div>'
)


def icon(short: str) -> str:
    return f"https://liquipedia.net/img/{short}.png"


def league(stage: str = "") -> dict:
    """Parsed tournament: the day suffix is dropped, a stage like "Playoffs" kept, the dark mode icon taken."""
    return {"name": f"{LEAGUE}{stage}", "url": f"{LEAGUE_URL}#Day", "icon": icon("league-darkmode")}


def test_parse_matches():
    matches = parse_matches(PAGE)

    def series(start, team1, team2, icon1, icon2, best_of=3, finished=False, score1=None, score2=None, tour=...):
        tour = league() if tour is ... else tour
        return {"start_time": start, "best_of": best_of, "team1": team1, "team2": team2, "team1_icon": icon1,
                "team2_icon": icon2, "tournament": tour, "finished": finished, "score1": score1,
                "score2": score2}  # fmt: skip

    assert matches == [
        series(NOW + 7200, "Team Alpha", "Beta Squad", icon("Alpha"), icon("BETA")),
        series(NOW + 3600, "Gamma", "Team Alpha", icon("GAM-dark"), icon("Alpha"), best_of=5),
        # No tournament line
        series(NOW + 9000, "TBD", "TBD", None, None, best_of=None, tour=None),
        series(NOW - 9000, "Beta Squad", "Delta", icon("BETA"), icon("DEL"), finished=True, score1=2, score2=1),
        series(NOW - 20000, "Gamma", "Team Alpha", icon("GAM"), icon("Alpha"), finished=True, score1=0, score2=2),
        # Forfeit: no map score
        series(
            NOW - 30000,
            "Delta",
            "Gamma",
            icon("DEL"),
            icon("GAM"),
            best_of=None,
            finished=True,
            tour=league(" - Playoffs"),
        ),
    ]


@pytest.mark.parametrize(
    ("liquipedia", "opendota"),
    [
        ("Direborn Esports", "DIREBORN"),
        ("LEGION (stack)", "LEGION"),
        ("Pibbles Corp", "Pibbles Corp."),
        ("The Bot$", "The Bot^$"),
        ("Selva Esports", "Selva Esports "),
        ("Team Spirit", "Spirit"),
    ],
)
def test_normalize_team_name_matches_spellings(liquipedia, opendota):
    assert normalize_team_name(liquipedia) == normalize_team_name(opendota)


def test_normalize_team_name_keeps_short_names():
    assert normalize_team_name("Team") == "team"
    assert normalize_team_name("Esports") == "esports"


def test_team_matcher_prefers_exact_name_then_latest_team(app):
    db = sqlite3.connect(f"{app.instance_path}/d2ba.sqlite")
    db.executemany(
        "INSERT INTO teams (team_id, name, tag, logo_url, last_match_time) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "LEGION", "LEGION", "https://logo/new.png", 200),
            (2, "Legion", "Legion", "https://logo/old.png", 100),
            (3, "Liquid", "TL", None, 300),
        ],
    )
    db.commit()
    db.close()

    with app.app_context():
        matcher = TeamMatcher()
        assert matcher.find("LEGION (stack)", None)["team_id"] == 1
        assert matcher.find("legion", None)["team_id"] == 1
        assert matcher.find("TL", "https://lp/tl.png") == {"name": "TL", "team_id": 3, "logo_url": "https://lp/tl.png"}
        assert matcher.find("Unknown", None) == {"name": "Unknown", "team_id": None, "logo_url": None}
        assert matcher.find("TBD", "https://lp/x.png")["team_id"] is None


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
    # No logo in the teams table, or not in it at all: the Liquipedia icon
    beta = {"name": "Beta Squad", "team_id": 22, "logo_url": icon("BETA")}
    gamma = {"name": "Gamma", "team_id": 33, "logo_url": "https://logo/gamma.png"}
    delta = {"name": "Delta", "team_id": None, "logo_url": icon("DEL")}
    tbd = {"name": "TBD", "team_id": None, "logo_url": None}
    assert response.get_json() == {
        "upcoming": [
            {"start_time": NOW + 3600, "best_of": 5, "team1": gamma, "team2": alpha, "tournament": league()},
            {"start_time": NOW + 7200, "best_of": 3, "team1": alpha, "team2": beta, "tournament": league()},
            {"start_time": NOW + 9000, "best_of": None, "team1": tbd, "team2": tbd, "tournament": None},
        ],
        "finished": [
            {
                "start_time": NOW - 9000,
                "best_of": 3,
                "team1": beta,
                "team2": delta,
                "tournament": league(),
                "score1": 2,
                "score2": 1,
            },
            {
                "start_time": NOW - 20000,
                "best_of": 3,
                "team1": gamma,
                "team2": alpha,
                "tournament": league(),
                "score1": 0,
                "score2": 2,
            },
            {
                "start_time": NOW - 30000,
                "best_of": None,
                "team1": delta,
                "team2": gamma,
                "tournament": league(" - Playoffs"),
                "score1": None,
                "score2": None,
            },
        ],
    }
    assert get.call_count == 1
    assert get.call_args.kwargs["params"]["page"] == "Liquipedia:Matches"
    assert get.call_args.kwargs["headers"]["User-Agent"].startswith("DotaBetAnalyzer/")
    assert "github" not in get.call_args.kwargs["headers"]["User-Agent"]


def test_second_call_uses_cache(client, fake_redis, known_teams):
    get_matches(client, liquipedia_response(PAGE))
    response, get = get_matches(client, liquipedia_response(""))

    assert len(response.get_json()["upcoming"]) == 3
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


def test_series_cached_without_tournament(client, fake_redis):
    """Series cached by a version before tournaments were parsed are served with a null tournament."""
    cached = {"start_time": NOW + 60, "best_of": 3, "team1": "A", "team2": "B", "team1_icon": None,
              "team2_icon": None, "finished": False, "score1": None, "score2": None}  # fmt: skip
    fake_redis.setex(CACHE_KEY, 600, json.dumps({"matches": [cached]}))

    response, _ = get_matches(client, liquipedia_response(""))

    assert response.get_json()["upcoming"][0]["tournament"] is None

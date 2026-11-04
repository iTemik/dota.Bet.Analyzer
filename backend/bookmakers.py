"""Match-winner odds of upcoming Dota 2 series from bookmaker sites, for the "Get odds from ..." buttons.

Pari (pari.ru, the Fonbet platform) has no public API docs, but its page reads the whole betting line as JSON from
its line servers without login or cookies. That answer is about 11.5 MB for all sports, so only the Dota 2 part is
kept, in Redis for CACHE_TTL: a button press costs at most one request, like a visitor opening the page.
Teams are found by name (exact, normalized, or the tag), in either order.
"""

from typing import Any, Optional

import requests

from backend.cache import cached_json
from backend.logging_config import setup_logging
from backend.matches import normalize_team_name

logger = setup_logging(__name__)

# Line servers the pari.ru page uses; the next one is tried when one fails
PARI_LINE_URLS = (
    "https://line-lb51-w.pb06e2-resources.com/events/listBase",
    "https://line-lb01-w.pb06e2-resources.com/events/listBase",
    "https://line-vk01-w.pb06e2-resources.ru/events/listBase",
)
PARI_PARAMS = {"lang": "ru", "scopeMarket": "2300"}
# A regular desktop browser, as the page itself would send
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
TIMEOUT = 30  # seconds; the answer is large
PARI_CACHE_KEY = "bookmaker:pari:dota2"
CACHE_TTL = 5 * 60  # seconds a fetched line is reused
ERROR_CACHE_TTL = 60  # a failed fetch is not repeated sooner

DOTA_SEGMENT = "dota 2"  # Dota tournaments are segments named "Dota 2. <tournament>. Bo3"
MATCH_LEVEL = 1  # level 1 events are series; deeper levels are maps and other sub-events
TEAM1_WIN = 921  # factor ids of the match winner market
TEAM2_WIN = 923


class OddsNotFound(LookupError):
    """The bookmaker has no upcoming series of these two teams; `matches` lists what it has."""

    def __init__(self, matches: list[str]) -> None:
        super().__init__("No upcoming series of these teams at the bookmaker")
        self.matches = matches


def _fetch_pari_line() -> dict[str, Any]:
    """The full Pari betting line JSON, from the first line server that answers.

    Raises:
        ConnectionError: When no server gave a JSON answer
    """
    errors = []
    for url in PARI_LINE_URLS:
        try:
            response = requests.get(url, params=PARI_PARAMS, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data
        except (requests.RequestException, ValueError) as e:
            logger.warning(f"Pari line {url} failed: {e}")
            errors.append(str(e))
    raise ConnectionError(f"Pari line could not be loaded: {errors[-1]}")


def parse_pari_line(line: dict[str, Any]) -> list[dict[str, Any]]:
    """Dota 2 series with match-winner odds from the Pari line JSON.

    Args:
        line: The listBase answer: `sports` (tournaments), `events` and `customFactors` (odds per event)

    Returns:
        Series soonest first: team1, team2, start_time (unix UTC), tournament, live, team1_odds, team2_odds;
        series without both winner odds are left out

    Raises:
        ValueError: When the answer has no `events` list
    """
    events = line.get("events")
    if not isinstance(events, list):
        raise ValueError("Pari line has no events")
    tournaments = {
        sport["id"]: sport.get("name", "")
        for sport in line.get("sports", [])
        if sport.get("kind") == "segment" and DOTA_SEGMENT in str(sport.get("name", "")).lower()
    }
    odds: dict[int, dict[int, float]] = {}
    for entry in line.get("customFactors", []):
        factors = {f.get("f"): f.get("v") for f in entry.get("factors", [])}
        if factors.get(TEAM1_WIN) and factors.get(TEAM2_WIN):
            odds[entry.get("e")] = {TEAM1_WIN: factors[TEAM1_WIN], TEAM2_WIN: factors[TEAM2_WIN]}
    series = [
        {
            "team1": event.get("team1", ""),
            "team2": event.get("team2", ""),
            "start_time": event.get("startTime"),
            "tournament": tournaments[event["sportId"]],
            "live": event.get("place") == "live",
            "team1_odds": odds[event["id"]][TEAM1_WIN],
            "team2_odds": odds[event["id"]][TEAM2_WIN],
        }
        for event in events
        if event.get("level") == MATCH_LEVEL and event.get("sportId") in tournaments and event.get("id") in odds
    ]
    return sorted(series, key=lambda s: s["start_time"] or 0)


def get_pari_series() -> list[dict[str, Any]]:
    """Dota 2 series at Pari, cached for CACHE_TTL (failures for ERROR_CACHE_TTL).

    Raises:
        ConnectionError: When the line could not be loaded or read (now or in the last minute)
    """
    series: list[dict[str, Any]] = cached_json(
        PARI_CACHE_KEY, CACHE_TTL, lambda: parse_pari_line(_fetch_pari_line()), error_ttl=ERROR_CACHE_TTL
    )
    return series


def _name_keys(*names: Optional[str]) -> set[str]:
    """Keys a team name (or tag) matches by: lower case and normalized."""
    keys = set()
    for name in names:
        if name and name.strip():
            keys.add(name.strip().lower())
            if normalize_team_name(name):
                keys.add(normalize_team_name(name))
    return keys


def find_odds(
    series: list[dict[str, Any]], team1: tuple[str, Optional[str]], team2: tuple[str, Optional[str]]
) -> dict[str, Any]:
    """Odds of the soonest series of two teams, in the order the teams were given.

    Args:
        series: Bookmaker series as parse_pari_line returns them
        team1: Name and tag of the first team
        team2: Name and tag of the second team

    Returns:
        team1_odds, team2_odds, start_time, tournament, live and names (the bookmaker's spelling, in our order)

    Raises:
        OddsNotFound: When no series has both teams
    """
    keys1, keys2 = _name_keys(*team1), _name_keys(*team2)
    for s in series:
        first, second = _name_keys(s["team1"]), _name_keys(s["team2"])
        if first & keys1 and second & keys2:
            swapped = False
        elif first & keys2 and second & keys1:
            swapped = True
        else:
            continue
        return {
            "team1_odds": s["team2_odds"] if swapped else s["team1_odds"],
            "team2_odds": s["team1_odds"] if swapped else s["team2_odds"],
            "start_time": s["start_time"],
            "tournament": s["tournament"],
            "live": s["live"],
            "names": [s["team2"], s["team1"]] if swapped else [s["team1"], s["team2"]],
        }
    raise OddsNotFound([f"{s['team1']} vs {s['team2']}" for s in series])

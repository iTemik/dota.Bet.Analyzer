"""Upcoming and recently finished pro series from Liquipedia, for the main page.

OpenDota has no schedule, so both lists come from one Liquipedia MediaWiki API request (`action=parse` of the Dota 2
matches page). Liquipedia allows one parse request per 30 seconds, so the parsed series are cached in Redis for
CACHE_TTL. Teams are matched by name to the d2ba.sqlite `teams` table for their OpenDota id and logo (no request).
"""

import json
import re
import time
from html.parser import HTMLParser
from typing import Any, ClassVar, Optional

import requests

from backend import __version__
from backend.logging_config import setup_logging
from backend.pro_players import get_d2ba_db
from backend.task_store import redis_client

logger = setup_logging(__name__)

LIQUIPEDIA_API = "https://liquipedia.net/dota2/api.php"
MATCHES_PAGE = "Liquipedia:Matches"
# Liquipedia asks for a custom User-Agent that names the project and blocks generic ones; no link or contact sent
USER_AGENT = f"DotaBetAnalyzer/{__version__}"
CACHE_KEY = "liquipedia:matches"
CACHE_TTL = 600  # seconds
ERROR_CACHE_TTL = 60  # a failed request is not repeated sooner, to stay inside Liquipedia's limits

LIQUIPEDIA_HOST = "https://liquipedia.net"  # team icon paths on the page are relative to it
# Match ticker markup: one `match-info` block per series, the two `opponent` blocks hold the team name link
# (`name` span) and icon, the scoreholder holds "2 : 1" (or "vs") and "(Bo3)"
MATCH_CLASS = "match-info"
OPPONENT_CLASS = "match-info-header-opponent"
SCORE_CLASS = "match-info-header-scoreholder"
# Tournament line: `league-icon-small-image` icons (lightmode and darkmode) and the name link
TOURNAMENT_CLASS = "match-info-tournament"
TOURNAMENT_NAME_CLASS = "match-info-tournament-name"
TOURNAMENT_ICON_CLASS = "league-icon-small-image"
MISSING_PAGE_SUFFIX = " (page does not exist)"  # title of a link to a team without a wiki page
BEST_OF_RE = re.compile(r"\bBo\s?(\d)\b")
SCORE_RE = re.compile(r"(\d+)\s*:\s*(\d+)")
# Day suffix of a tournament name ("EPC Season 3 - October 26"); the time column shows the date already
DAY_SUFFIX_RE = re.compile(r"\s+-\s+[A-Z][a-z]+ \d{1,2}$")


class _Node:
    """Element of the parsed page: tag, attributes and children (nodes or text)."""

    def __init__(self, tag: str, attrs: dict[str, str]) -> None:
        self.tag = tag
        self.attrs = attrs
        self.children: list[Any] = []

    @property
    def classes(self) -> list[str]:
        """CSS classes of the element."""
        return self.attrs.get("class", "").split()

    def text(self, sep: str = "") -> str:
        """All text inside the element, the pieces of child elements joined with sep."""
        return sep.join(c if isinstance(c, str) else c.text(sep) for c in self.children)

    def find_all(self, predicate: Any) -> list["_Node"]:
        """Descendants matching the predicate, in document order (matches are not searched further)."""
        found = []
        for child in self.children:
            if isinstance(child, _Node):
                if predicate(child):
                    found.append(child)
                else:
                    found.extend(child.find_all(predicate))
        return found


class _TreeBuilder(HTMLParser):
    """Builds a _Node tree; void and unclosed elements are tolerated."""

    VOID: ClassVar[set[str]] = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        node = _Node(tag, {k: v or "" for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def _has_class(*names: str) -> Any:
    return lambda node: any(c in node.classes for c in names)


def _url(src: str) -> Optional[str]:
    """Absolute URL of a link or image path on the page."""
    return f"{LIQUIPEDIA_HOST}{src}" if src.startswith("/") else (src or None)


def _team(node: _Node) -> dict[str, Optional[str]]:
    """Team of an opponent block: full name (the name link title, else the shown text) and Liquipedia icon URL."""
    names = node.find_all(_has_class("name"))
    links = names[0].find_all(lambda n: n.tag == "a") if names else []
    title = links[0].attrs.get("title", "").removesuffix(MISSING_PAGE_SUFFIX) if links else ""
    name = (title or (names[0].text() if names else node.text())).strip()
    # The app has a dark background, so take the dark mode icon when the team has light and dark ones
    dark = node.find_all(_has_class("team-template-darkmode"))
    images = (dark or [node])[0].find_all(lambda n: n.tag == "img")
    return {"name": name, "icon": _url(images[0].attrs.get("src", "")) if images else None}


def _tournament(node: _Node) -> Optional[dict[str, Optional[str]]]:
    """Tournament of a match block: shown name without a day suffix, Liquipedia page URL and dark mode icon."""
    blocks = node.find_all(_has_class(TOURNAMENT_CLASS))
    names = blocks[0].find_all(_has_class(TOURNAMENT_NAME_CLASS)) if blocks else []
    name = DAY_SUFFIX_RE.sub("", " ".join(names[0].text().split())) if names else ""
    if not name:
        return None
    links = names[0].find_all(lambda n: n.tag == "a")
    icons = blocks[0].find_all(_has_class(TOURNAMENT_ICON_CLASS))
    dark = [i for i in icons if "darkmode" in i.classes]
    images = (dark or icons or [_Node("span", {})])[0].find_all(lambda n: n.tag == "img")
    return {
        "name": name,
        "url": _url(links[0].attrs.get("href", "")) if links else None,
        "icon": _url(images[0].attrs.get("src", "")) if images else None,
    }


def _parse_match(node: _Node) -> Optional[dict[str, Any]]:
    """One series from its match block, or None when it lacks a start time or two teams."""
    timers = node.find_all(lambda n: "data-timestamp" in n.attrs)
    teams = [_team(t) for t in node.find_all(_has_class(OPPONENT_CLASS))]
    if not timers or len(teams) != 2 or not all(t["name"] for t in teams):
        return None
    try:
        start_time = int(timers[0].attrs["data-timestamp"])
    except ValueError:
        return None
    score_nodes = node.find_all(_has_class(SCORE_CLASS))
    score_text = " ".join(score_nodes[0].text(" ").split()) if score_nodes else ""
    best_of = BEST_OF_RE.search(score_text)
    score = SCORE_RE.search(score_text)
    return {
        "start_time": start_time,
        "best_of": int(best_of.group(1)) if best_of else None,
        "team1": teams[0]["name"],
        "team2": teams[1]["name"],
        "team1_icon": teams[0]["icon"],
        "team2_icon": teams[1]["icon"],
        "tournament": _tournament(node),
        "finished": timers[0].attrs.get("data-finished") == "finished",
        "score1": int(score.group(1)) if score else None,
        "score2": int(score.group(2)) if score else None,
    }


def parse_matches(html: str) -> list[dict[str, Any]]:
    """All series on the Liquipedia matches page (upcoming and recent tabs).

    Args:
        html: Rendered page HTML from the parse API

    Returns:
        Series with start_time, best_of, team1/team2 names, team1_icon/team2_icon, tournament (name, url, icon;
        None when missing), finished and score1/score2 (None when not shown, e.g. "FF : W" for a forfeit)
    """
    builder = _TreeBuilder()
    builder.feed(html)
    matches = (_parse_match(node) for node in builder.root.find_all(_has_class(MATCH_CLASS)))
    return [m for m in matches if m is not None]


def fetch_matches_from_liquipedia() -> list[dict[str, Any]]:
    """Fetch and parse the Liquipedia matches page (one request).

    Returns:
        Series as returned by parse_matches

    Raises:
        ConnectionError: If Liquipedia could not be reached or answered with an error
        ValueError: If the answer has no page HTML
    """
    params = {"action": "parse", "page": MATCHES_PAGE, "prop": "text", "format": "json", "formatversion": "2"}
    headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
    try:
        resp = requests.get(LIQUIPEDIA_API, params=params, headers=headers, timeout=30)
    except requests.RequestException as e:
        raise ConnectionError(f"Failed to reach Liquipedia: {e}") from e
    if resp.status_code != 200:
        raise ConnectionError(f"HTTP {resp.status_code} from Liquipedia")
    try:
        html = resp.json()["parse"]["text"]
    except (ValueError, KeyError, TypeError) as e:
        raise ValueError(f"Unexpected Liquipedia response: {e}") from e
    if isinstance(html, dict):  # formatversion 1 shape
        html = html.get("*", "")
    return parse_matches(str(html))


def _cached_matches() -> list[dict[str, Any]]:
    """Parsed series from Redis, fetched from Liquipedia when the cache is empty.

    A failure is cached for ERROR_CACHE_TTL and raised again from the cache, so a broken page or network
    does not turn every page load into a new Liquipedia request.
    """
    try:
        cached = redis_client.get(CACHE_KEY)
    except Exception as e:
        logger.warning(f"Redis unavailable for matches cache: {e}")
        cached = None
    if cached is not None:
        data: dict[str, Any] = json.loads(cached)
        if "error" in data:
            raise ConnectionError(data["error"])
        matches: list[dict[str, Any]] = data["matches"]
        return matches

    try:
        matches = fetch_matches_from_liquipedia()
    except (ConnectionError, ValueError) as e:
        _cache_put({"error": str(e)}, ERROR_CACHE_TTL)
        raise ConnectionError(str(e)) from e
    _cache_put({"matches": matches}, CACHE_TTL)
    return matches


def _cache_put(data: dict[str, Any], ttl: int) -> None:
    try:
        redis_client.setex(CACHE_KEY, ttl, json.dumps(data))
    except Exception as e:
        logger.warning(f"Failed to cache matches: {e}")


def normalize_team_name(name: str) -> str:
    """Name key that ignores case, punctuation, a "(stack)"-like note, a "Team" prefix and an "Esports" suffix.

    Liquipedia and OpenDota spell names differently: "Direborn Esports" / "DIREBORN", "LEGION (stack)" / "LEGION".
    """
    key = re.sub(r"\(.*?\)", "", name.lower())
    key = re.sub(r"[^a-z0-9]", "", key)
    key = key.removeprefix("team") if len(key) > len("team") else key
    return key.removesuffix("esports") or key


class TeamMatcher:
    """Finds a Liquipedia team in the teams table: exact name, then normalized name, then tag.

    Among equal keys the team with the latest match wins. The table is read once per instance.
    """

    def __init__(self) -> None:
        self.by_name: dict[str, tuple[int, Optional[str]]] = {}
        self.by_key: dict[str, tuple[int, Optional[str]]] = {}
        self.by_tag: dict[str, tuple[int, Optional[str]]] = {}
        rows = get_d2ba_db().execute(
            "SELECT team_id, name, tag, logo_url FROM teams ORDER BY COALESCE(last_match_time, 0), team_id"
        )
        for team_id, name, tag, logo_url in rows:
            team = (team_id, logo_url)
            if name:
                self.by_name[name.strip().lower()] = team
                if normalize_team_name(name):
                    self.by_key[normalize_team_name(name)] = team
            if tag:
                self.by_tag[tag.strip().lower()] = team

    def find(self, name: str, icon: Optional[str]) -> dict[str, Any]:
        """Team entry for the API: the name plus OpenDota team_id and logo_url when the name matches.

        Args:
            name: Team name on Liquipedia
            icon: Liquipedia icon URL, the logo when the teams table has none

        Returns:
            name, team_id (None when not found) and logo_url
        """
        if name.upper() == "TBD":
            return {"name": name, "team_id": None, "logo_url": None}
        lower = name.strip().lower()
        team = self.by_name.get(lower) or self.by_key.get(normalize_team_name(name)) or self.by_tag.get(lower)
        team_id, logo_url = team if team else (None, None)
        return {"name": name, "team_id": team_id, "logo_url": logo_url or icon}


def get_matches(now: Optional[int] = None) -> dict[str, list[dict[str, Any]]]:
    """Upcoming series soonest first and finished series newest first.

    Ongoing series (started, not finished) are in neither list.

    Args:
        now: Current unix time (for tests)

    Returns:
        `upcoming` and `finished` lists of series with start_time, best_of, team1, team2 (name, team_id, logo_url),
        tournament (name, url, icon or None); finished series also carry score1 and score2

    Raises:
        ConnectionError: If the series could not be loaded from Liquipedia
    """
    now = now if now is not None else int(time.time())
    matches = _cached_matches()
    matcher = TeamMatcher()
    teams: dict[str, dict[str, Any]] = {}

    def entry(match: dict[str, Any], with_score: bool) -> dict[str, Any]:
        for key in ("team1", "team2"):
            if match[key] not in teams:
                teams[match[key]] = matcher.find(match[key], match.get(f"{key}_icon"))
        result = {
            "start_time": match["start_time"],
            "best_of": match["best_of"],
            "team1": teams[match["team1"]],
            "team2": teams[match["team2"]],
            # .get: series cached by an older version have no tournament
            "tournament": match.get("tournament"),
        }
        if with_score:
            result["score1"] = match["score1"]
            result["score2"] = match["score2"]
        return result

    upcoming = sorted(
        (m for m in matches if not m["finished"] and m["start_time"] > now), key=lambda m: m["start_time"]
    )
    finished = sorted((m for m in matches if m["finished"]), key=lambda m: m["start_time"], reverse=True)
    return {
        "upcoming": [entry(m, with_score=False) for m in upcoming],
        "finished": [entry(m, with_score=True) for m in finished],
    }

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
# Liquipedia asks for a custom User-Agent with contact info and blocks generic ones
USER_AGENT = f"DotaBetAnalyzer/{__version__} (https://github.com/iTemik/dota.Bet.Analyzer)"
CACHE_KEY = "liquipedia:matches"
CACHE_TTL = 600  # seconds
ERROR_CACHE_TTL = 60  # a failed request is not repeated sooner, to stay inside Liquipedia's limits
FINISHED_LIMIT = 30

# Containers of one series: the classic match ticker table and the newer match-info block
MATCH_CLASSES = ("infobox_matches_content", "match-info")
TEAM_CLASS = "team-template-text"
SCORE_CLASSES = ("versus", "match-info-header-scoreholder")
BEST_OF_RE = re.compile(r"\bBo\s?(\d)\b")
SCORE_RE = re.compile(r"(\d+)\s*:\s*(\d+)")


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


def _team_name(node: _Node) -> str:
    """Full team name: the link title (page name) if any, else the shown text."""
    links = node.find_all(lambda n: n.tag == "a")
    title = links[0].attrs.get("title", "") if links else ""
    return (title or node.text()).strip()


def _parse_match(node: _Node) -> Optional[dict[str, Any]]:
    """One series from its match block, or None when it lacks a start time or two teams."""
    timers = node.find_all(lambda n: "data-timestamp" in n.attrs)
    teams = [_team_name(t) for t in node.find_all(_has_class(TEAM_CLASS))]
    teams = [t for t in teams if t]
    if not timers or len(teams) < 2:
        return None
    try:
        start_time = int(timers[0].attrs["data-timestamp"])
    except ValueError:
        return None
    text = " ".join(node.text(" ").split())
    best_of = BEST_OF_RE.search(text)
    score_nodes = node.find_all(_has_class(*SCORE_CLASSES))
    score = SCORE_RE.search(" ".join(score_nodes[0].text(" ").split())) if score_nodes else None
    return {
        "start_time": start_time,
        "best_of": int(best_of.group(1)) if best_of else None,
        "team1": teams[0],
        "team2": teams[1],
        "finished": timers[0].attrs.get("data-finished") == "finished",
        "score1": int(score.group(1)) if score else None,
        "score2": int(score.group(2)) if score else None,
    }


def parse_matches(html: str) -> list[dict[str, Any]]:
    """All series on the Liquipedia matches page, each once.

    Args:
        html: Rendered page HTML from the parse API

    Returns:
        Series with start_time, best_of, team1/team2 names, finished and score1/score2 (None when not shown)
    """
    builder = _TreeBuilder()
    builder.feed(html)
    series: dict[tuple, dict[str, Any]] = {}
    for node in builder.root.find_all(_has_class(*MATCH_CLASSES)):
        match = _parse_match(node)
        if match is not None:
            # The page can show a series in more than one list (e.g. upcoming and featured)
            series.setdefault((match["start_time"], match["team1"], match["team2"]), match)
    return list(series.values())


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


def _find_team(name: str) -> dict[str, Any]:
    """Team entry for the API: the name plus OpenDota team_id and logo_url when the name matches the teams table."""
    if name.upper() == "TBD":
        return {"name": name, "team_id": None, "logo_url": None}
    row = (
        get_d2ba_db()
        .execute(
            """
            SELECT team_id, logo_url FROM teams
            WHERE LOWER(name) = LOWER(?) OR LOWER(tag) = LOWER(?)
            ORDER BY LOWER(name) = LOWER(?) DESC, COALESCE(last_match_time, 0) DESC
            LIMIT 1
            """,
            (name, name, name),
        )
        .fetchone()
    )
    return {"name": name, "team_id": row[0] if row else None, "logo_url": row[1] if row else None}


def get_matches(now: Optional[int] = None) -> dict[str, list[dict[str, Any]]]:
    """Upcoming series soonest first and finished series newest first.

    Ongoing series (started, not finished) are in neither list.

    Args:
        now: Current unix time (for tests)

    Returns:
        `upcoming` and `finished` lists of series with start_time, best_of, team1, team2 (name, team_id, logo_url);
        finished series also carry score1 and score2

    Raises:
        ConnectionError: If the series could not be loaded from Liquipedia
    """
    now = now if now is not None else int(time.time())
    matches = _cached_matches()
    teams: dict[str, dict[str, Any]] = {}

    def entry(match: dict[str, Any], with_score: bool) -> dict[str, Any]:
        for name in (match["team1"], match["team2"]):
            if name not in teams:
                teams[name] = _find_team(name)
        result = {
            "start_time": match["start_time"],
            "best_of": match["best_of"],
            "team1": teams[match["team1"]],
            "team2": teams[match["team2"]],
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
        "finished": [entry(m, with_score=True) for m in finished[:FINISHED_LIMIT]],
    }

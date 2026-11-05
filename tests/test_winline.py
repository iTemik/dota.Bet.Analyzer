"""Tests for the Winline frame decoder (backend.winline), the WebSocket fetch and GET /api/odds/winline."""

import gzip
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import websocket

from backend.bookmakers import (
    WINLINE_CACHE_KEY,
    WINLINE_HELLO,
    get_winline_series,
    parse_winline_frames,
)
from backend.cache import cache_get
from backend.winline import WinlineLine

FIXTURES = Path(__file__).parent / "fixtures" / "winline"
MENU = gzip.decompress((FIXTURES / "step16_menu.bin.gz").read_bytes())
PREMATCH = (FIXTURES / "step3_dota.bin").read_bytes()
LIVE = (FIXTURES / "step4_live.bin").read_bytes()
EXPECTED = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))["series"]


def expected_series() -> list[tuple]:
    """The series decoded on the capture day by the reference decoder, as comparable tuples."""
    return sorted(
        (
            s["team1"],
            s["team2"],
            int(datetime.fromisoformat(s["start_utc"].replace("Z", "+00:00")).timestamp()),
            s["live"],
            s["p1"],
            s["p2"],
            s["tournament"],
        )
        for s in EXPECTED
    )


def as_tuples(series: list[dict]) -> list[tuple]:
    """Decoded series as comparable tuples."""
    return sorted(
        (s["team1"], s["team2"], s["start_time"], s["live"], s["team1_odds"], s["team2_odds"], s["tournament"])
        for s in series
    )


def test_decodes_captured_frames_like_the_reference():
    """Menu, prematch and live frames give the 17 Dota 2 series with the site's match-winner odds."""
    series = parse_winline_frames([PREMATCH, LIVE, MENU])
    assert as_tuples(series) == expected_series()
    assert [s["start_time"] for s in series] == sorted(s["start_time"] for s in series)
    assert sum(s["live"] for s in series) == 2


def test_menu_gives_market_layouts():
    """The menu frame fills the market layout table (853 markets in the capture)."""
    line = WinlineLine()
    line.add_frame(MENU)
    assert len(line.tips) == 853
    assert line.tips[1366] == 1


def test_prematch_without_menu_uses_known_dota_markets():
    """The Dota-only prematch frame decodes with the built-in Dota market layouts."""
    line = WinlineLine()
    line.add_frame(PREMATCH)
    assert len(line.dota_series()) == 15


def test_unknown_market_without_menu_fails():
    """A market whose layout is unknown stops the frame with ValueError (format changed)."""
    line = WinlineLine()
    line.tips.clear()
    with pytest.raises(ValueError, match="unknown market"):
        line.add_frame(PREMATCH)


def test_truncated_frame_fails():
    """A frame cut short is a ValueError, not a crash."""
    with pytest.raises(ValueError, match="could not be read"):
        WinlineLine().add_frame(PREMATCH[:200])


def fake_socket(frames: list[bytes]) -> MagicMock:
    """A WebSocket that answers recv() with the gzipped frames, then times out."""
    ws = MagicMock()
    ws.recv.side_effect = [gzip.compress(f) for f in frames] + [websocket.WebSocketTimeoutException("idle")]
    return ws


def test_fetch_reads_one_session_and_caches():
    """One WebSocket session (hello frames sent, closed after the needed frames); the next call uses the cache."""
    ws = fake_socket([MENU, PREMATCH, LIVE, LIVE])
    with patch("backend.bookmakers.websocket.create_connection", return_value=ws) as connect:
        first = get_winline_series()
        second = get_winline_series()
    assert connect.call_count == 1
    assert [c.args[0] for c in ws.send.call_args_list] == list(WINLINE_HELLO)
    assert ws.recv.call_count == 3  # stops once menu, prematch and live arrived
    ws.close.assert_called_once()
    assert first == second == cache_get(WINLINE_CACHE_KEY)
    assert len(first) == 17


def test_fetch_without_prematch_fails_and_is_cached():
    """No prematch frame before the socket goes quiet: ConnectionError, and the failure is cached."""
    ws = fake_socket([MENU, LIVE])
    with patch("backend.bookmakers.websocket.create_connection", return_value=ws) as connect:
        with pytest.raises(ConnectionError):
            get_winline_series()
        with pytest.raises(ConnectionError):
            get_winline_series()
    assert connect.call_count == 1


def test_connect_failure_is_connection_error():
    """A socket that cannot be opened is a ConnectionError."""
    with patch("backend.bookmakers.websocket.create_connection", side_effect=OSError("refused")):
        with pytest.raises(ConnectionError, match="could not be reached"):
            get_winline_series()


def test_winline_route_200(client):
    """GET /api/odds/winline returns the odds in the requested order (Winline writes names in capitals)."""
    ws = fake_socket([MENU, PREMATCH, LIVE])
    with patch("backend.bookmakers.websocket.create_connection", return_value=ws):
        response = client.get("/api/odds/winline?team1=GamerLegion&team2=Yellow%20Submarine&tag1=GL")
    assert response.status_code == 200
    assert response.get_json() == {
        "team1_odds": 1.31,
        "team2_odds": 3.5,
        "start_time": 1793887200,  # 2026-11-05 14:00 UTC
        "tournament": "EPL Masters",
        "live": False,
        "names": ["GAMERLEGION", "YELLOW SUBMARINE"],
    }


def test_winline_route_404(client):
    """No series of the pair: 404 ODDS_NOT_FOUND listing Winline's series."""
    ws = fake_socket([MENU, PREMATCH, LIVE])
    with patch("backend.bookmakers.websocket.create_connection", return_value=ws):
        response = client.get("/api/odds/winline?team1=Unknown&team2=GamerLegion")
    assert response.status_code == 404
    assert "YELLOW SUBMARINE vs GAMERLEGION" in response.get_json()["details"]["matches"]


def test_winline_route_422(client):
    """A missing team is a validation error."""
    assert client.get("/api/odds/winline?team2=GamerLegion").status_code == 422


def test_winline_route_503(client):
    """The socket fails: 503 FAILED_TO_FETCH_ODDS."""
    with patch("backend.bookmakers.websocket.create_connection", side_effect=OSError("refused")):
        response = client.get("/api/odds/winline?team1=A&team2=B")
    assert response.status_code == 503
    assert response.get_json()["code"] == "FAILED_TO_FETCH_ODDS"

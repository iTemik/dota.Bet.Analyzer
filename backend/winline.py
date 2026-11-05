"""Decoder for the binary frames of the winline.ru WebSocket line (no network here; backend.bookmakers fetches).

Winline's page gets its betting line over a WebSocket of gzipped binary frames. Gunzipped, a frame starts with a
uint16 step; the steps used here are 16 (menu: market layouts), 3 (prematch line) and 4 (live line). Field order
follows the site's own JavaScript parsers; tests/fixtures/winline/NOTES.md has the full layout. Records carry no
lengths, so an unknown record stops the frame with ValueError (the format changed).
"""

import struct
from typing import Any

MENU_STEP = 16
PREMATCH_STEP = 3
LIVE_STEP = 4
PREMATCH_OFFSET = 16  # header bytes after the step (zeros); the last byte of the frame is not a record
LIVE_OFFSET = 12
DOTA2_COUNTRY = 20086  # Dota 2 championships have this idCountry (inside sport 205, esports)
MATCH_WINNER = 1366  # idTipMarket of the series winner, values [P1, P2]
MOSCOW_OFFSET = 3 * 3600  # dates are the epoch of Moscow wall time
LINE_REMOVED = 5  # live line state of a removed line
EVENT_LAST_STATE = 3  # live event records with a higher state end after the state field
# idTipMarket -> idTipEventSrc of the Dota 2 markets, used until a menu frame arrives
DOTA_TIPS = {284: 71, 1366: 1, 1368: 151, 1422: 4, 1423: 3}


class _Reader:
    """Little-endian reader over one frame body."""

    def __init__(self, data: bytes, pos: int = 0) -> None:
        self.data = data
        self.pos = pos

    def _take(self, fmt: str) -> int:
        value: int = struct.unpack_from(fmt, self.data, self.pos)[0]
        self.pos += struct.calcsize(fmt)
        return value

    def u8(self) -> int:
        return self._take("<B")

    def u16(self) -> int:
        return self._take("<H")

    def u32(self) -> int:
        return self._take("<I")

    def i32(self) -> int:
        return self._take("<i")

    def skip(self, count: int) -> None:
        self.pos += count

    def text(self) -> str:
        """uint16 length + UTF-8; the value ends at the first 0x1b byte."""
        length = self.u16()
        raw = self.data[self.pos : self.pos + length].split(b"\x1b")[0]
        self.pos += length
        return raw.decode("utf-8", "replace")

    def skip_text(self, count: int = 1) -> None:
        for _ in range(count):
            self.skip(self.u16())


def frame_step(frame: bytes) -> int:
    """The step id of a gunzipped frame (0 for a frame too short to have one)."""
    return struct.unpack_from("<H", frame)[0] if len(frame) >= 2 else 0


class WinlineLine:
    """Dota 2 series and their match-winner odds gathered from menu, prematch and live frames."""

    def __init__(self) -> None:
        self.tips: dict[int, int] = dict(DOTA_TIPS)  # idTipMarket -> idTipEventSrc
        self.championships: dict[int, tuple[int, str]] = {}  # id -> (idCountry, name)
        self.events: dict[int, dict[str, Any]] = {}
        self.winner_odds: dict[int, list[float]] = {}  # event id -> [P1, P2]
        self.deleted: set[int] = set()

    def add_frame(self, frame: bytes) -> None:
        """Read one gunzipped frame; other steps are ignored.

        Args:
            frame: Gunzipped WebSocket message, starting with the uint16 step

        Raises:
            ValueError: When a record cannot be read (the format changed)
        """
        try:
            step = frame_step(frame)
            if step == MENU_STEP:
                self._read_menu(_Reader(frame, 2))
            elif step == PREMATCH_STEP:
                self._read_prematch(_Reader(frame, 2 + PREMATCH_OFFSET), len(frame) - 1)
            elif step == LIVE_STEP:
                self._read_live(_Reader(frame, 2 + LIVE_OFFSET))
        except (struct.error, IndexError) as e:
            raise ValueError(f"Winline frame could not be read: {e}") from e

    def _read_menu(self, r: _Reader) -> None:
        """Step 16: sports (skipped), then the tip lines that give each market's line layout."""
        for _ in range(r.u32()):
            r.skip(8)
            r.skip_text(10)
        for _ in range(r.u32()):
            market = r.u32()
            r.skip_text()
            r.skip(8)  # favorite, countV
            self.tips[market] = r.u32()
            r.skip_text(31)  # freeTextR + 30 outcome labels

    def _read_prematch(self, r: _Reader, end: int) -> None:
        """Step 3 records; championships and lines belong to the last championship and event read."""
        championship = event = -1
        while r.pos < end:
            kind = r.u8()
            if kind == 1:  # country
                r.skip(8)
                r.skip_text()
                r.skip(10)
            elif kind == 2:
                championship = r.u32()
                r.skip(4)  # idSport
                country = r.u32()
                self.championships[championship] = (country, r.text())
                r.skip(21)
            elif kind in (3, 34):
                event = r.u32()
                r.skip(14)  # idRadar, idNative, provider, category, idLive, linesAvailability, 2 bytes
                r.skip(r.u16())  # widgets
                owner = r.u32() if kind == 34 else championship
                date = r.u32()
                r.skip(2)
                teams = [r.text(), r.text()]
                self.events.setdefault(event, {}).update(
                    {"championship": owner, "date": date, "teams": teams, "live": False}
                )
            elif kind in (4, 43):
                self._read_prematch_line(r, kind == 43, event)
            elif kind == 31:
                changed = r.u32()
                self.events.setdefault(changed, {})["date"] = r.u32()
            elif kind == 32:
                self.deleted.add(r.u32())
            elif kind == 33:
                r.skip(6)
            elif kind == 42:
                r.skip(4)
            else:
                raise ValueError(f"unknown prematch record {kind} at {r.pos}")

    def _read_prematch_line(self, r: _Reader, update: bool, current_event: int) -> None:
        """Step 3 line: the market's idTipEventSrc decides which fields follow."""
        r.skip(4)  # line id
        event = r.u32() if update else current_event
        market = r.u16()
        r.skip(2)  # cash margin
        margin = r.u16() / 10000
        src = self.tips.get(market)
        if src is None:
            raise ValueError(f"unknown market {market} (no menu frame)")
        if src in (3, 6, 61):
            r.skip(1)  # favorite
        has_koef = src in (3, 4, 6, 7, 61, 71)
        if has_koef:
            r.skip(2)
        count = 2 + (1 if src in (2, 5, 51) else 2 if src == 9 else 0)
        values = [r.u16() / 100 for _ in range(count)]
        if market == MATCH_WINNER and not has_koef and src not in (51, 151):
            self.winner_odds[event] = [_with_margin(v, margin) for v in values[:2]]

    def _read_live(self, r: _Reader) -> None:
        """Step 4 records (live and starting soon); live odds need no margin step."""
        while r.pos < len(r.data):
            kind = r.u8()
            if kind == 2:
                championship = r.u32()
                r.skip(8)  # idSport, idSort
                country = r.u32()
                r.skip(1)
                self.championships.setdefault(championship, (country, r.text()))
                r.skip(9)
            elif kind in (3, 4):
                self._read_live_event(r, kind == 3)
            elif kind == 5:
                self._read_live_line(r)
            elif kind == 6:
                r.skip(5)
            else:
                raise ValueError(f"unknown live record {kind} at {r.pos}")

    def _read_live_event(self, r: _Reader, new: bool) -> None:
        """Step 4 event (new or update); records of finished events end after the state field."""
        event = r.i32()
        if new:
            r.skip(10)  # idRadar, idNative, provider, category
        r.skip(r.u16())  # widgets
        r.skip(3)
        if r.i32() > EVENT_LAST_STATE:
            return
        entry = self.events.setdefault(event, {})
        if new:
            entry["championship"] = r.u32()
            entry["teams"] = [r.text(), r.text()]
            entry["date"] = r.u32()
        entry["live"] = True
        r.skip_text()  # time
        r.skip(5)  # cards, feed
        r.skip_text(3)  # score, set scores, info
        r.skip(1)

    def _read_live_line(self, r: _Reader) -> None:
        """Step 4 line; removed lines end after the state field."""
        r.skip(4)
        if r.u8() == LINE_REMOVED:
            return
        event = r.u32()
        values = [r.u16() / 100 for _ in range(r.u8())]
        market = r.u16()
        koef = r.text()
        r.skip(1)
        if market == MATCH_WINNER and koef == "" and len(values) >= 2:
            self.winner_odds[event] = values[:2]

    def dota_series(self) -> list[dict[str, Any]]:
        """Dota 2 series with match-winner odds, soonest first, in the same shape as Pari's.

        Returns:
            team1, team2, start_time (unix UTC), tournament, live, team1_odds, team2_odds
        """
        series = []
        for event_id, event in self.events.items():
            championship = self.championships.get(event.get("championship", -1))
            odds = self.winner_odds.get(event_id)
            if not championship or championship[0] != DOTA2_COUNTRY or not odds or "teams" not in event:
                continue
            if event_id in self.deleted:
                continue
            series.append(
                {
                    "team1": event["teams"][0],
                    "team2": event["teams"][1],
                    "start_time": event["date"] - MOSCOW_OFFSET if event.get("date") else None,
                    "tournament": championship[1],
                    "live": bool(event.get("live")),
                    "team1_odds": odds[0],
                    "team2_odds": odds[1],
                }
            )
        return sorted(series, key=lambda s: s["start_time"] or 0)


def _with_margin(value: float, margin: float) -> float:
    """Prematch odds as the site shows them: stretched by its margin, then clamped like the page does."""
    if margin != 1 and value > 1:
        value = round(1 + (value - 1) * margin, 2)
    if value >= 10:
        return float(int(value))
    return 1.0 if 0 < value < 1.01 else value

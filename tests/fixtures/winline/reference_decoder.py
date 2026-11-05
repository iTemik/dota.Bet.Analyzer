# ruff: noqa
# mypy: ignore-errors
"""Decode Winline WS frames (steps 16 menu, 3 prematch, 4 live) per the site's main.js parsers.

Usage: python winline_decode.py <frames_dir> [out.json]
Frames: gunzipped WS messages, first 2 bytes = uint16 LE step.
  step 16 (_n):  sports, tip lines (idTipMarket -> idTipEventSrc, needed to size step-3 lines)
  step 3  (Qe):  prematch, body from offset 16 (after the 2-byte step), last byte ignored
  step 4  (qe):  live, body from offset 12
Dates: uint32 epoch of Moscow wall time -> UTC = raw - 10800.
"""

import datetime as dt
import glob
import json
import os
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8")
DOTA2_COUNTRY = 20086
MATCH_WINNER = 1366
MSK = 10800
# idTipMarket -> idTipEventSrc for the Dota 2 markets seen 2026-11-05 (fallback when no step-16 frame)
DOTA_TIPS = {284: 71, 1366: 1, 1368: 151, 1422: 4, 1423: 3}


class R:
    """Little-endian reader mirroring main.js readUnsigned*/readUTF."""

    def __init__(self, b: bytes, seek: int = 0):
        self.b, self.s = b, seek

    def _u(self, fmt: str, n: int) -> int:
        v = struct.unpack_from(fmt, self.b, self.s)[0]
        self.s += n
        return v

    def u8(self) -> int:
        return self._u("<B", 1)

    def u16(self) -> int:
        return self._u("<H", 2)

    def u32(self) -> int:
        return self._u("<I", 4)

    def i32(self) -> int:
        return self._u("<i", 4)

    def utf(self) -> str:
        n = self.u16()
        raw = self.b[self.s : self.s + n].split(b"\x1b")[0]
        self.s += n
        return raw.decode("utf-8", "replace")

    def widgets(self) -> None:
        n = self.u16()  # Re(): length-prefixed widget block (not `self.s += self.u16()`: reads s first)
        self.s += n


def parse_menu(r: R) -> dict[int, dict]:
    """Step 16: return tip lines by id (idTipEventSrc decides the step-3 line layout)."""
    for _ in range(r.u32()):  # sports: id, sort, name, 9 strings
        r.i32(), r.i32()
        for _ in range(10):
            r.utf()
    tips = {}
    for _ in range(r.u32()):
        t = {
            "id": r.u32(),
            "sports": r.utf(),
            "favorite": r.u32(),
            "countV": r.u32(),
            "src": r.u32(),
            "freeTextR": r.utf(),
        }
        t["R"] = [r.utf() for _ in range(30)]
        tips[t["id"]] = t
    return tips


def apply_margin(v: list[float], m: float, tip_id: int) -> list[float]:
    """ze.setCoeff for prematch (isLive=0): stretch odds by the site margin, then clamp."""
    if m == 1:
        return v
    v = [round(1 + (x - 1) * m, 2) if x > 1 else x for x in v]
    if tip_id in (114, 115, 116, 117, 181) and len(v) >= 3:
        s = sum(1 / x for x in v[:3] if x)
        p0, p1, p2 = v[0], v[1], v[2]
        v[0] = 1 / (s - 1 / p2) if p2 else 1
        v[1] = 1 / (s - 1 / p1) if p1 else 1
        v[2] = 1 / (s - 1 / p0) if p0 else 1
        v[:3] = [round(max(x, 1), 2) for x in v[:3]]
    return [(float(int(x)) if x >= 10 else (1.0 if x < 1.01 else x)) if x > 0 else x for x in v]


def read_pre_line(r: R, tips: dict, update: bool, cur_event: int) -> dict:
    """Step 3.4 / 3.43 line."""
    ln = {"id": r.u32()}
    ln["idEvent"] = r.u32() if update else cur_event
    ln["idTipMarket"] = r.u16()
    r.u16()  # cash margin
    margin = r.u16() / 1e4  # site margin
    tip = tips.get(ln["idTipMarket"])
    if tip is None:
        raise ValueError(f"unknown idTipMarket {ln['idTipMarket']} (need step 16)")
    src = tip["src"]
    ln["koef"] = ""
    if src in (3, 6, 61):
        ln["favorite"] = r.u8()
    if src in (3, 4, 6, 7):
        ln["koef"] = str(r.u16() / 100)
    elif src in (61, 71):
        ln["koef"] = "1/" + str(r.u16() / 100)
    elif src in (51, 151):
        ln["koef"] = "1"
    n = 2 + (1 if src in (2, 5, 51) else 2 if src == 9 else 0)
    raw = [r.u16() / 100 for _ in range(n)]
    ln["V_raw"], ln["margin"] = raw, margin
    ln["V"] = apply_margin(list(raw), margin, ln["idTipMarket"])
    return ln


def parse_prematch(r: R, tips: dict, db: dict, spans: list | None = None) -> None:
    """Step 3 body from seek 16. spans, if given, gets (start, end, substep, championship id) per record."""
    end = len(r.b) - 1  # Qe reads the last byte separately; it is not a record
    cur_champ = cur_event = -1
    while r.s < end:
        if spans is not None and spans and spans[-1][1] is None:
            spans[-1][1] = r.s
        if spans is not None:
            spans.append([r.s, None, r.b[r.s], cur_champ])
        st = r.u8()
        if spans is not None and st == 2:
            spans[-1][3] = struct.unpack_from("<I", r.b, r.s)[0]
        if st == 1:
            c = {
                "id": r.u32(),
                "isRegion": r.u32(),
                "name": r.utf(),
                "idSort": r.u32(),
                "continent": r.u8(),
                "x": r.u16(),
                "y": r.u16(),
                "showGroupID": r.u8(),
            }
            db["countries"][c["id"]] = c
        elif st == 2:
            c = {
                "id": r.u32(),
                "idSport": r.u32(),
                "idCountry": r.u32(),
                "name": r.utf(),
                "idSort": r.i32(),
                "code": r.u32(),
                "countSpecial": r.u32(),
                "levelOnSite": r.u8(),
                "idSortLevel": r.u32(),
                "idSortNewLevel": r.u32(),
            }
            db["champs"][c["id"]] = c
            cur_champ = c["id"]
        elif st in (3, 34):
            e = {
                "id": r.u32(),
                "idRadar": r.u32(),
                "idNative": r.u32(),
                "provider": r.u8(),
                "category": r.u8(),
                "idLive": r.u8(),
                "linesAvailability": r.u8(),
            }
            r.u8(), r.u8()
            r.widgets()
            e["idChampionship"] = r.u32() if st == 34 else cur_champ
            e["date_raw"] = r.u32()
            e |= {"count_add_line": r.u8(), "isOD": r.u8(), "members": [r.utf(), r.utf()], "src": "pre"}
            db["events"].setdefault(e["id"], {}).update(e)
            cur_event = e["id"]
        elif st in (4, 43):
            ln = read_pre_line(r, tips, st == 43, cur_event)
            db["lines"][(ln["idEvent"], ln["id"])] = ln | {"src": "pre"}
        elif st == 31:
            i, d = r.u32(), r.u32()
            db["events"].setdefault(i, {"id": i})["date_raw"] = d
        elif st == 32:
            db["deleted"].add(r.u32())
        elif st == 33:
            r.u32(), r.u8(), r.u8()
        elif st == 42:
            r.u32()
        else:
            raise ValueError(f"unknown step 3.{st} at {r.s}")


def parse_live(r: R, db: dict) -> None:
    """Step 4 body from seek 12 (see winline_decode_step4.py)."""
    while r.s < len(r.b):
        st = r.u8()
        if st == 2:
            c = {
                "id": r.u32(),
                "idSport": r.u32(),
                "idSort": r.i32(),
                "idCountry": r.u32(),
                "code": r.u8(),
                "name": r.utf(),
                "levelOnSite": r.u8(),
                "idSortLevel": r.u32(),
                "idSortNewLevel": r.u32(),
            }
            db["champs"].setdefault(c["id"], c)
        elif st in (3, 4):
            e = {"id": r.i32()}
            if st == 3:
                e |= {"idRadar": r.u32(), "idNative": r.u32(), "provider": r.u8(), "category": r.u8()}
            r.widgets()
            e |= {"isOD": r.u8(), "_skip": r.u8(), "duration": r.u8(), "state": r.i32()}
            if e["state"] > 3:
                continue
            if st == 3:
                e["idChampionship"] = r.u32()
                e["members"] = [r.utf(), r.utf()]
                e["date_raw"] = r.u32()
            e["time"] = r.utf()
            r.s += 4  # cards
            e |= {"feed": r.u8(), "score": r.utf(), "setScores": r.utf(), "addInfo": r.utf(), "lineCount": r.u8()}
            ev = db["events"].setdefault(e["id"], {})
            ev.update(e)
            ev["live"] = True
        elif st == 5:
            ln = {"id": r.u32(), "state": r.u8()}
            if ln["state"] == 5:
                continue
            ln["idEvent"] = r.u32()
            ln["V"] = [r.u16() / 100 for _ in range(r.u8())]
            ln["idTipMarket"] = r.u16()
            ln["koef"] = r.utf()
            ln["favorite"] = r.u8()
            db["lines"][(ln["idEvent"], ln["id"])] = ln | {"src": "live"}
        elif st == 6:
            r.u32(), r.u8()
        else:
            raise ValueError(f"unknown step 4.{st} at {r.s}")


def main() -> None:
    """Decode all frames in a directory and print/save Dota 2 series with match-winner odds."""
    frames_dir = sys.argv[1]
    db = {"countries": {}, "champs": {}, "events": {}, "lines": {}, "deleted": set()}
    tips: dict = {k: {"id": k, "src": v} for k, v in DOTA_TIPS.items()}
    files = sorted(glob.glob(os.path.join(frames_dir, "frame_*.bin")))
    for fn in files:  # menu first: step-3 lines need it
        raw = open(fn, "rb").read()
        if struct.unpack_from("<H", raw)[0] == 16:
            tips = parse_menu(R(raw[2:], 0))
    print(
        "tip lines:",
        len(tips),
        "match winner tip:",
        {k: v for k, v in tips.get(MATCH_WINNER, {}).items() if k != "R"}
        | {"R": tips.get(MATCH_WINNER, {}).get("R", [])[:3]},
    )
    pre_in = {}
    for fn in files:
        raw = open(fn, "rb").read()
        step = struct.unpack_from("<H", raw)[0]
        try:
            if step == 3:
                before = set(db["events"])
                parse_prematch(R(raw[2:], 16), tips, db)
                pre_in[os.path.basename(fn)] = len(set(db["events"]) - before)
            elif step == 4:
                parse_live(R(raw[2:], 12), db)
        except Exception as ex:
            print("parse stop", fn, ex)
    print("step-3 frames (new events):", pre_in)
    dota_champs = {i: c for i, c in db["champs"].items() if c["idCountry"] == DOTA2_COUNTRY}
    print("champs", len(db["champs"]), "events", len(db["events"]), "lines", len(db["lines"]))
    print("dota champs:", [(c["id"], c["name"]) for c in dota_champs.values()])
    by_ev: dict[int, list] = {}
    for (eid, _), ln in db["lines"].items():
        by_ev.setdefault(eid, []).append(ln)
    series = []
    for e in db["events"].values():
        if e.get("idChampionship") not in dota_champs or e["id"] in db["deleted"]:
            continue
        mw = [ln for ln in by_ev.get(e["id"], []) if ln["idTipMarket"] == MATCH_WINNER and ln["koef"] in ("", "0.0")]
        start = dt.datetime.fromtimestamp(e["date_raw"] - MSK, dt.UTC) if e.get("date_raw") else None
        series.append(
            {
                "id": e["id"],
                "championship": dota_champs[e["idChampionship"]]["name"],
                "members": e.get("members"),
                "start_utc": start.isoformat() if start else None,
                "live": bool(e.get("live")),
                "in_prematch": e.get("src") == "pre",
                "score": e.get("score"),
                "P1": mw[0]["V"][0] if mw else None,
                "P2": mw[0]["V"][1] if mw else None,
                "match_winner_line": mw[0] if mw else None,
                "line_count": len(by_ev.get(e["id"], [])),
            }
        )
    series.sort(key=lambda s: s["start_utc"] or "")
    for s in series:
        print(
            f"  {s['start_utc']} {'LIVE' if s['live'] else 'pre '} pre3={int(s['in_prematch'])} "
            f"{s['members']} P1={s['P1']} P2={s['P2']} lines={s['line_count']} [{s['championship']}]"
        )
    if len(sys.argv) > 2:
        json.dump(
            {"championships": list(dota_champs.values()), "series": series},
            open(sys.argv[2], "w", encoding="utf-8"),
            ensure_ascii=False,
            indent=1,
        )


if __name__ == "__main__":
    main()

# Winline WebSocket fixtures

Captured 2026-11-05 from `wss://wss.winline.ru/data_ng?client=newsite&nb=true` (the site's own socket, no login).
Field names follow the site's `main.js` parsers (`_n` step 16, `Qe` step 3, `qe` step 4).

| File | What |
|---|---|
| `step16_menu.bin.gz` | Step-16 menu frame (140 837 bytes gunzipped): sports + tip lines. Gzipped here only to keep the repo small. |
| `step3_dota.bin` | Step-3 prematch frame trimmed to the Dota 2 records: 1 country, 3 championships, 15 events, 65 lines. |
| `step4_live.bin` | One whole step-4 live frame (same capture as the menu) with 2 live Dota 2 series and their 1366 lines. |
| `expected.json` | Dota 2 series decoded from the two frames above (team1, team2, start_utc, live, p1, p2, tournament). |
| `reference_decoder.py` | The decoder used to produce `expected.json`. Reference only, the app does not import it. The only changes are the `ruff: noqa` / `mypy: ignore-errors` header and black formatting. |

## Frame format and handshake

- Every server message is a binary frame, gzip compressed (`1f 8b` magic). Gunzipped, the first 2 bytes are the
  step id (uint16 LE); the rest is the step body. All numbers are little endian.
- Strings (`utf`): uint16 byte length + UTF-8 bytes. The value ends at the first `0x1b` byte inside it, if any.
- Odds are uint16 / 100. Dates are uint32 epoch of Moscow wall time: UTC = raw - 10800.
- Handshake: open the socket with the query above; no cookies or auth needed. Only server frames were recorded, so
  no client message is known to be needed: the server pushed everything below by itself. In order:
  step 20000 (payment hosts), 1180, **16 (menu)**, **3 (full prematch line, ~870 KB)**, 7, 1181, **4 (full live line)**,
  51, 44 (client IP, do not store it), 86, 1348, 110, 1399, 38, then a stream of small step-4 updates (every ~0.3-0.6 s)
  and occasional small step-3 updates. Step 3 can only be parsed after step 16; step 4 can be parsed alone.
- Dota 2 = sport 205 (Киберспорт), country 20086 inside it. A championship is Dota 2 when `idCountry == 20086`.

## Step 16 (menu), body from offset 2

```
u32 sport_count
  sport: i32 id, i32 sort, 10 × utf (name, then 9 period/unit names; 205 → "Киберспорт", "FT", "матч", "матч", "", "карта", ...)
u32 tip_count                                    (853 in this capture)
  tip line: u32 idTipMarket, utf sports ("205,"), u32 favorite, u32 countV, u32 idTipEventSrc, utf freeTextR,
            30 × utf R (outcome labels, 1366 → "1", "2", "", ...)
```

`idTipEventSrc` (the `src` field) decides how a step-3 line with that `idTipMarket` is laid out (see step 3), so
step 3 cannot be parsed without it. Dota 2 tips here:

| idTipMarket | idTipEventSrc | countV | freeTextR |
|---|---|---|---|
| 1366 | 1 | 2 | Победитель (@NP@) (match winner: P1/P2) |
| 1368 | 151 | 2 | @[a]P@ победитель (map winner) |
| 1422 | 4 | 2 | Тотал карт [a] (@NP@) |
| 1423 | 3 | 2 | Фора карт [a] (@NP@) (favorite = 1) |
| 284 | 71 | 2 | @[a]P@ тотал [b] убийств |

`reference_decoder.DOTA_TIPS` keeps this map as a fallback when no step-16 frame is at hand.

## Step 3 (prematch), body from offset 16

Bytes 2-15 are a header (zeros here) and the last byte of the frame is read separately: it is not a record.
Then records until the end, each a u8 substep:

- `1` country: u32 id, u32 isRegion, utf name, u32 idSort, u8 continent, u16 x, u16 y, u8 showGroupID
- `2` championship: u32 id, u32 idSport, u32 idCountry, utf name, i32 idSort, u32 code, u32 countSpecial,
  u8 levelOnSite, u32 idSortLevel, u32 idSortNewLevel. Becomes the current championship.
- `3` / `34` event: u32 id, u32 idRadar, u32 idNative, u8 provider, u8 category, u8 idLive, u8 linesAvailability,
  u8, u8, widgets (u16 length + bytes), [`34` only: u32 idChampionship, else the current one], u32 date_raw,
  u8 count_add_line, u8 isOD, utf team1, utf team2. Becomes the current event.
- `4` / `43` line: u32 id, [`43` only: u32 idEvent, else the current event], u16 idTipMarket, u16 cash margin,
  u16 site margin (/10000), then by the tip's idTipEventSrc:
  - src 3, 6, 61: u8 favorite
  - src 3, 4, 6, 7: u16 koef (/100, the handicap/total); src 61, 71: u16 → koef "1/x"; src 51, 151: koef "1"; else ""
  - values: 2 × u16, +1 for src 2, 5, 51, +2 for src 9
  - shown odds = `1 + (v - 1) × margin` rounded to 2 places (when margin != 1 and v > 1), then v >= 10 → int,
    v < 1.01 → 1 (see `apply_margin`; tips 114-117, 181 also renormalise 3-way odds).
- `31` date change: u32 event id, u32 date_raw · `32` deleted: u32 event id · `33`: u32, u8, u8 · `42`: u32

Match winner = line with idTipMarket 1366 and empty koef: P1 = V[0], P2 = V[1].

## Step 4 (live), body from offset 12

Bytes 2-13 are three u32 (meaning unknown, skipped). Records, u8 substep:

- `2` championship: u32 id, u32 idSport, i32 idSort, u32 idCountry, u8 code, utf name, u8 levelOnSite,
  u32 idSortLevel, u32 idSortNewLevel (field order differs from step 3)
- `3` new event / `4` event update: i32 id, [`3`: u32 idRadar, u32 idNative, u8 provider, u8 category],
  widgets (u16 length + bytes), u8 isOD, u8, u8 duration, i32 state. If state > 3 the record ends here.
  Else [`3`: u32 idChampionship, utf team1, utf team2, u32 date_raw], utf time, 4 bytes cards, u8 feed, utf score,
  utf setScores, utf addInfo, u8 lineCount.
- `5` line: u32 id, u8 state (5 = removed, record ends), u32 idEvent, u8 count, count × u16 values (/100),
  u16 idTipMarket, utf koef, u8 favorite. Live odds are final (no margin step). Match winner = 1366 with koef "".
- `6`: u32, u8

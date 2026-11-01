# Code review, November 2026

Step IDs (Q1, C1, D2...) are used in PR titles and descriptions. Status is updated by each step's PR.

## Step index

| ID | Step | Size | Status |
|---|---|---|---|
| Hints | `.claude/codebase-map.md` for Claude | S | PR #97 |
| Q1 | `start_task` helper, unique task ids | S | Planned |
| Q2 | `cached_json` Redis cache helper, one Redis client | S | Planned |
| Q3 | `@job` decorator for cache jobs | S | Planned |
| Q4 | Remove `POST .../sync` endpoints (use `/jobs/{name}/run`) | S | Planned |
| Q5 | Guard test: no direct `requests`, no real HTTP in tests | S | Planned |
| T1 | Fake Redis in tests | S | Planned |
| T2 | Small frontend unit tests | S | Planned |
| F5 | `api.ts` fetch helper, fixes lost Compare error text | S | Planned |
| F6 | `<Collapsible>` component | S | Optional |
| F7 | TS types generated from OpenAPI | M | Optional |
| B7 | `backend/models.py` | S | Optional |
| B8 | Rank errors not cached | S | Planned |
| B9 | Short lineups negative cache | S | Optional |
| B10 | Swagger error example helper | S | Optional |
| C1 | CSS colour tokens | S-M | Planned |
| C2 | One `<Bar>` component | S | Planned |
| C3 | Dark team search dropdown | S | Planned |
| C4 | Guard test: no colour literals | S | Planned |
| D1 | One `db.py`, remove dead `opendota.sqlite` code | S | Planned |
| D2 | SQLite WAL + busy timeout (**DB**, needs approval) | S | Planned |
| D3 | Test: migrations match schema files | S | Planned |
| R1 | Split routes into modules | M | Optional |
| R2 | Config and dead code cleanup | S | Optional |

Reviewed `main` at `d1a8c92` (after PR #96). All 523 backend and 162 frontend tests pass. Earlier refactoring plan (B1-B7, F1-F4): B1-B5 and F1-F4 are merged; B6 is replaced by Q4 and B7 is kept below.

Each step is one small PR. Sizes: **S** under ~150 changed lines, **M** 150-400. Steps marked **DB** change the database and need the owner's approval. The order at the end is the agreed plan.

## Short answers

- **Refactor, reuse, simplify:** the biggest wins are one Redis cache helper (meta and matches copy the same 40 lines), one frontend `api.ts` (4 copies of "fetch and throw the backend message", one of them broken), and removing the 3 old sync endpoints that bypass the job system.
- **Colour scheme:** pages mostly match, but there is no palette. 4 greens, 6 reds and 2 blues are hard-coded, the team search dropdown uses a light theme on the dark page, and the Compare progress bar is a light-grey inline bar while the other bars are dark. Fix: CSS colour tokens in one place (step C1).
- **Single DB?** Keep two SQLite files. `d2ba.sqlite` is a cache that can be deleted at any time, `predictions.sqlite` is user data to back up; they never join. Do merge the connection code into one module and add WAL mode, because 4 processes now write to `d2ba.sqlite`.
- **Same task manager for all OpenDota requests?** Not everything through Celery. The single gate that matters is already there: every OpenDota request passes `opendota.get_json` and the Redis rate limiter. What is missing is a written rule plus helpers, so a new feature picks the right one of three paths (below), and a test that fails when someone calls `requests.get` directly.
- **Tests worth adding:** a fake Redis in tests (without Redis running, 17 tests spend 70 of the suite's 85 s retrying a Redis connection; with Redis running, tests write progress keys into the dev Redis), a "no direct HTTP" guard, the rank-cache bug, the frontend error message bug, and `format.ts`/`series.ts` units.
- **Code to remove:** `db.py` + `opendota_schema.sql` + `schema.txt` + `generate_schema.py` (serve an `opendota.sqlite` nobody reads), the 3 `POST .../sync` endpoints, unused `Errors` entries and config values, the Vite template leftovers in `index.css`.

## Bugs found on the way

1. **A failed rank request is cached as "no rank" for 24 h.** `stats.get_rank` returns `None` on any OpenDota error, and `task_store.get_rank_cached` stores that `None` for `PLAYER_RANK_CACHE_TTL` (1 day). One timeout hides a player's rank for a day. Fix: `get_rank` raises on errors, the cache stores only real answers (step B8).
2. **The Compare error message is always lost.** `App.tsx` `handleCheck`: the `throw new Error(errorMsg)` sits inside the `try` whose `catch` replaces it with "HTTP error! status: N". The backend message ("Team not found"...) never reaches the page. Fixed by F5.
3. **Two Compare clicks in the same second share a task id.** `players_statistics` builds `task_{int(time.time())}`, `_create_team_stats` builds `task_{team_id}_{int(time.time())}`. The second is fine for two different teams, the first collides. Fix: `uuid4().hex` in one `new_task_id()` helper (step Q1).
4. **Incomplete lineups are re-requested on every Compare.** `rosters.get_match_lineups` caches a lineup only with 10 players; a match with an anonymous player falls back to `/matches/{id}` (one request per match, up to 40 per team) every time. Fix: also cache short lineups, or remember "incomplete" for a day (step B9, **DB** only if we add a column; a Redis negative cache needs no DB change).
5. **`get_d2ba_db` ignores `DATABASE_FILENAME`** and hard-codes `d2ba.sqlite`; `Config.DATABASE_FILENAME`, `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` are never read (`celery_app.py` builds its own URLs). Harmless now, confusing later. Fixed by D1 / R2.
6. **`.claude/claude.md` may not load in cloud sessions.** Claude Code looks for `CLAUDE.md`; on Windows the lowercase name matches, on Linux (cloud sessions) it does not. Its "PowerShell only, no bash" rule is also wrong in cloud sessions. Fixed in PR #97.

## Queueing rules (answer to "same task manager")

Today there are three ways work reaches OpenDota, and each is right for its case:

| Path | Used by | Goes through |
|---|---|---|
| Flask request, synchronous | `/statistics` team lookup + roster, head-to-head, meta/matches on a cold cache | `get_json` (user priority) |
| Celery default queue, with progress | Compare player matches + ranks (`players_statistics_task`) | `get_json` + `ProgressReporter` |
| Celery `background` queue, scheduled | pro players, heroes, teams, hero meta, Liquipedia matches (`jobs.JOBS`) | `get_json(background=True)` + job lock |

Moving the synchronous calls into Celery would add a progress stream to things that take 1-3 requests, for no gain: the rate limiter already orders them across all processes. So the rule should be:

1. **Every HTTP call** goes through `opendota.get_json` (or `matches.fetch_matches_from_liquipedia` for Liquipedia). Never `requests.get`.
2. **1-3 requests a user waits for** → call in the route, user priority.
3. **More requests, or per-player loops** → a Celery task on the default queue with `ProgressReporter`, started by one helper.
4. **Data that goes stale on a clock** → a `Job` in `jobs.JOBS` (`background=True`), read from the cache by the route; the route never fetches it except on a cold cache.

What is missing to make this easy and enforced:

- **Q1 `start_task` helper (S).** `task_store.start_task(task, **kwargs) -> task_id`: makes a uuid id, writes the "Queued" progress, calls `.delay`. Replaces the two hand-written copies (route and `stats._create_team_stats`) and fixes bug 3.
- **Q2 `cached_json` helper (S).** In a new `backend/cache.py`: `cached_json(key, ttl, fetch, error_ttl=60)` with the "error cached for 60 s and raised again" rule. `meta.cached_hero_stats`, `matches._cached_matches`, `get_matches_cached` and `get_rank_cached` all become 3-5 lines. One Redis client for the app instead of 4 (`task_store`, `jobs`, `rate_limit`, and the two modules that import `task_store.redis_client`).
- **Q3 `@job` decorator (S).** Registering a job is now a private `_run_x` function plus an entry in the `JOBS` tuple. A decorator `@job(name, title, stale_after)` next to the fetch code keeps both in one place.
- **Q4 Remove the old sync endpoints (S).** `POST /api/pro-players/sync`, `/api/heroes/sync` and `/api/teams/sync` run in the Flask process at user priority, skip the job lock and the job status, and the frontend no longer calls them. `POST /api/jobs/{name}/run` covers them; the one extra, `teams?full=true`, becomes `POST /api/jobs/teams/run?full=true`. This also removes `teams_sync._sync_lock` (a per-process lock that cannot stop the worker and Flask from syncing at once) and B6 from the old proposal. API change: 3 endpoints removed.
- **Q5 Guard test (S).** One pytest that fails when a module other than `opendota.py` and `matches.py` imports `requests`, and an autouse fixture that makes any real `requests.get` raise in tests (the network guard offered earlier).

## Cache and DB layout

**Now:**
- `instance/d2ba.sqlite` (cache, migrations in `backend/migrations/`): pro_players, teams, team_matches (+ team_matches_sync TTL), match_players (forever), heroes, sync_state (job last success).
- `instance/predictions.sqlite` (user data, `backend/migrations/predictions/`): team_snapshots, predictions.
- Redis db 0: Celery broker and results. Redis db 1: progress/results (1 h), player matches (1 h), ranks (1 day), hero stats (2 h), Liquipedia matches (30 min), job status and locks, rate limiter slots and daily counter.
- `opendota.sqlite` via `db.py`: created by the app, never read.

**Single DB or two:** keep two. Reasons: the cache can be deleted to fix any cache problem (as with the heroes table clash) without touching predictions; backing up means copying one small file; the two have separate migration folders already; nothing joins across them (snapshots store JSON). One file would only save one connection helper, which D1 does anyway.

**Steps:**
- **D1 One `db.py` (S).** Replace the dead `db.py` with `get_cache_db()` and `get_user_db()` (today `pro_players.get_d2ba_db` and `predictions_db.get_predictions_db`; old names kept as aliases at first, so test patches keep working). The cache connection no longer lives in `pro_players.py`, which `jobs`, `rosters`, `ratings` and `teams_sync` import only for it. Delete `opendota_schema.sql`, `schema.txt`, `scripts/generate_schema.py` and their 2 tests. Uses `DATABASE_FILENAME`.
- **D2 WAL + busy timeout (S).** Flask, 2 workers and Beat (through jobs) write to `d2ba.sqlite`. Default rollback journal + 5 s timeout risks "database is locked" while the teams job writes 20k rows. `PRAGMA journal_mode=WAL` once per file and `timeout=15` on connect. No schema change, but it changes the file format on disk (adds `-wal`/`-shm` files), so I flag it **DB** for approval.
- **D3 Schema file check (S).** `d2ba_schema.sql` and `predictions_schema.sql` are documentation only; nothing applies them, so they drift. A test that runs all migrations on an empty file and compares tables and columns with the schema file keeps them honest.

## Colour scheme

Checked `index.css`, `App.css`, `TeamAutocomplete.css`, inline styles and `format.ts`.

| Use | Values now |
|---|---|
| Positive (good value, won) | `#6b9d7a` cells and bars, `#7ddc95` text and budget bar |
| Negative (bad value, lost) | `#9d6b6b` cells, `#c46a6a` bars, `#ff8a8a` text, `#ff6b6b` buttons/errors, `#ffd0d0`, `#d32f2f` in autocomplete |
| Accent | `#667eea` (gradient, active tab), `#4a90e2` and `#646cff` (autocomplete focus, Vite button hover) |
| Gold (ultra meta, "before prediction" tag) | `#ffd257` + two `rgba(255,200,0,…)` |
| Surfaces | ~10 different `rgba(255,255,255,0.06…0.35)` and `rgba(0,0,0,0.15…0.5)` |

Off-scheme spots: the team search dropdown (white box, grey text, blue focus: the only light-theme element), the Compare progress bar (inline `#e0e0e0` track, unlike `.data-bar` and `.meta-bar`), `index.css` light-mode media query and button hover from the Vite template, and `format.ts` duplicating the two CSS colours in JS.

- **C1 Colour tokens (S-M).** All colours as variables in `index.css :root`: `--accent`, `--pos`, `--neg`, `--pos-text`, `--neg-text`, `--gold`, `--surface-1/2/3`, `--border`, `--error`. Replace every literal. `format.ts` returns class names (`cell-pos`/`cell-neg`) instead of hex values. Drop the Vite light-mode block (the page is always the dark gradient). Visual result: identical except the merged near-duplicates.
- **C2 One bar component (S).** `<Bar value tone>` for the Compare progress, data status and Meta bars; removes the inline styled bar in `App.tsx`.
- **C3 Dark team search dropdown (S).** `TeamAutocomplete.css` on the tokens; screenshot before/after for approval.
- **C4 Guard test (S).** A vitest test that fails when a `.css`/`.tsx` file outside `index.css` contains a hex or `rgba(` literal, so new pages stay on the palette.

## Frontend reuse

- **F5 `api.ts` (S).** Move `requestJson` out of `predictions.ts` into `src/api.ts` (with `postJson`/`putJson`), use it in `App.tsx`, `PredictionPanel.tsx` (its own `postJson`), `TeamAutocomplete.tsx` and `DataStatus.tsx`. Fixes bug 2. Add a test that the backend message is shown.
- **F6 Collapsible section (S).** The raw JSON blocks repeat the header/toggle/content markup; one `<Collapsible title>` component.
- **F7 Types from OpenAPI (M, optional).** `types.ts` is hand-written and can drift from `schemas.py`. `openapi-typescript` against `/api/openapi.json` generates them; a CI step fails on a diff. Worth it only if API changes keep coming.

## Backend simplify

- **B7 Models module (S)** from the old proposal: `TeamStats`, `MatchStats`, `MatchesSummary`, `StatsResponse`, `Player` into `backend/models.py`; removes the `pro_players` → `stats` import cycle workaround.
- **B8 Rank errors (S).** Bug 1.
- **B9 Short lineups (S).** Bug 4, Redis negative cache for a day, no DB change.
- **B10 Error examples helper (S, optional).** ~300 lines of `@bp.alt_response(... example={...})` repeat the same shape; `error_response(status, Errors.X, "description")` builds the example from `Errors`. Swagger output unchanged.
- **R1 Split routes (M, optional).** `dota_bet_analyzer.py` (1,300 lines) into `routes/statistics.py`, `routes/jobs.py`, `routes/heroes.py`, `routes/predictions.py`, `routes/teams.py`, one blueprint each registered in `__init__.py`. Test patch paths move, so only if shorter files are wanted; the codebase map already covers the file.
- **R2 Config cleanup (S).** Remove unused config values, read Celery URLs from `Config`, strip the BOM at the top of `dota_bet_analyzer.py`, remove unused `Errors` entries (`INVALID_ACCOUNT_ID`, `MISSING_ACCOUNT_IDS`, `TOO_MANY_PLAYERS`, `UNSUPPORTED_METHOD`), `rosters.get_match_lineup` (tests only), `PRO_PLAYERS_README.md` (describes the old `opendota.sqlite` split).

## Tests worth adding

| Test | Why | Step |
|---|---|---|
| Fake Redis for all tests (`fakeredis`, autouse) | 85 s → ~15 s without Redis (CI has none); no test keys in the dev Redis | T1 |
| No direct `requests` import, real HTTP raises in tests | Enforces the queueing rule | Q5 |
| Rank error not cached | Bug 1 | B8 |
| Compare shows the backend error text | Bug 2 | F5 |
| Two Compares in one second get different task ids | Bug 3 | Q1 |
| `cached_json`: hit, miss, error cached 60 s, Redis down | New shared helper | Q2 |
| Migrations vs schema files | Docs drift | D3 |
| `format.ts`, `series.ts`, `BetOutcome`, `RowInfo` units | Only covered through big component tests | T2 |
| No colour literals outside tokens | Palette stays one | C4 |

- **T1 Fake Redis (S).** Adds `fakeredis` to dev requirements; one conftest fixture swaps the shared client (easiest after Q2 makes it one client). No production change.
- **T2 Small frontend units (S).**

## Recommended order

1. Hints doc (PR #97, with this document)
2. Q2 cache helper, then T1 fake Redis (fast tests make the rest cheaper)
3. Q1 + Q5 (task helper, guard test)
4. Q4 remove old sync endpoints (API change)
5. F5 `api.ts` (fixes the error message bug), B8 rank bug
6. C1 tokens, then C2-C4
7. D1, then D2 (**DB** approval), D3
8. The rest if still wanted: B7, B9, B10, F6, F7, R1, R2

## AI hints

Added in PR #97 as `.claude/codebase-map.md`, imported from `.claude/CLAUDE.md` so every Claude session (Windows and cloud) loads it. It is a terse map: modules, endpoints, request paths, caches and keys, DB tables, test fixtures, and "to add X, touch Y" recipes. When a step above lands, its PR updates the map.

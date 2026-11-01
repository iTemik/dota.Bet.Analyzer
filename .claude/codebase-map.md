# Codebase map (for Claude; terse on purpose, read before exploring)

Update this file in the same PR when a module, endpoint, cache key, table, job or rule below changes.
Refactoring plan with step IDs (Q1, C1, D2...): `docs/code-review-2026-11.md`; a step PR updates its Status row.

## Run / check
- Backend tests: `python -m pytest tests/ -q` (~85 s without Redis: tests retry Redis in update_progress). Frontend: `cd frontend && npx vitest run`. Lint: `python -m pre_commit run --all-files`; frontend `npx eslint` has ~24 old errors, don't chase them.
- `npm run dev` = check Redis, apply migrations (scripts/init_d2ba_db.py), then 5 processes: flask :5000, celery worker (default queue), celery worker `-Q background`, celery beat, vite :5173 (proxies /api).
- Never edit `backend/VERSION`, `frontend/src/version.ts`, package versions: `.github/workflows/version.yml` bumps them on main.
- Tests never hit the network: everything is mocked (see Tests). OpenDota/Liquipedia are blocked from cloud sessions anyway.

## Backend (`backend/`, Flask + flask-smorest, one blueprint `bp` in dota_bet_analyzer.py, prefix /api)
| Module | Holds |
|---|---|
| `__init__.py` | create_app (singleton unless test_config), 422 handler → ErrorSchema, registers bp, queues due jobs at startup (not in TESTING) |
| `config.py` | Config from env: REDIS_HOST/PORT, OPENDOTA_MIN_INTERVAL 1.2, OPENDOTA_DAILY_LIMIT 1800, LIQUIPEDIA_MIN_INTERVAL 30 |
| `dota_bet_analyzer.py` | ALL routes (~1300 lines) + `players_statistics_task` (Celery, default queue) + stream generators |
| `celery_app.py` | `celery`, BACKGROUND_QUEUE="background", beat: check_due_jobs_task every 60 s |
| `opendota.py` | ONLY OpenDota HTTP: `get_json(path, params, timeout, on_wait, background)` → JSON or raises `OpenDotaError(status, code, message)`; `opendota_get` raw; retry 403/429/timeouts; `OPENDOTA_LIMITER`; `is_radiant(slot)` |
| `rate_limit.py` | `RateLimiter` (Redis slot+lock+UTC day counter, shared by all processes), `DailyLimitReached`, `report_waits(cb)` ctx |
| `jobs.py` | Cache job registry `JOBS` (pro_players 24h, heroes 7d, teams 24h, hero_meta 1h, matches 10min), `queue_job`, `queue_job_if_due`, `run_job`, status in Redis, last success in `sync_state` |
| `task_store.py` | Redis db1 client `redis_client`, `update_progress`, `ProgressReporter`, `store_results`/`get_results`, `get_matches_cached` (1h), `get_rank_cached` (1d), progress pub/sub |
| `stats.py` | Compare: `compute_statistics` (sync, in request) → per team explorer lookup, team info, roster, rating change, starts `players_statistics_task`; models TeamStats, MatchStats, MatchesSummary, StatsResponse, RankTally; `get_matches`, `get_rank`, `get_team_matches_summary` |
| `rosters.py` | `resolve_roster`, `classify_roster` (core rule), `get_team_league_matches` (SQLite, 2h TTL), `get_match_lineups` (SQLite forever, explorer batches of 20), `window_start`, `DAY_SECONDS` |
| `ratings.py` | `window_rating_change` Elo back-calc, no requests |
| `pro_players.py` | `get_d2ba_db()` (cache DB connection lives HERE), `Player`, pro players fetch/store, `get_players_by_team`, teams fetch/store (full /teams pages) |
| `teams_sync.py` | `run_teams_sync(full)`: incremental 2 explorer queries, full ~22 pages |
| `heroes.py` | /constants/heroes → `heroes` table, `list_heroes` |
| `meta.py` | /heroStats → Redis `opendota:hero_stats:v2` (2h, errors 60s), `MetaParams`, `compute_meta`, `get_meta` |
| `matches.py` | Liquipedia parse → Redis `liquipedia:matches` (30min, errors 60s), `LIQUIPEDIA_LIMITER`, `TeamMatcher` (name → teams table), own `requests.get` (only allowed exception) |
| `head_to_head.py` | from cached team matches, 0-1 requests |
| `snapshots.py`, `predictions.py`, `predictions_db.py` | user data in predictions.sqlite; `get_predictions_db()` |
| `helpers.py` | `Errors` registry (ErrorDefinition code+message), `ApiError`, `api_error(status, Errors.X, exc=None, **details)` → (Response, status), explorer SQL builder, `ExplorerTeam` |
| `schemas.py` | marshmallow schemas; `pydantic_to_marshmallow` derives ErrorSchema/TeamStatsSchema/StatsResponseSchema/PlayerSchema from pydantic |
| `db.py`, `opendota_schema.sql`, `schema.txt` | DEAD (opendota.sqlite, never read). Don't extend |
| `d2ba_schema.sql`, `predictions_schema.sql` | docs only, not applied; keep in sync with migrations |

## Request paths (queueing rules; pick one for new work)
1. Every HTTP call → `opendota.get_json` (Liquipedia: `matches.fetch_matches_from_liquipedia`). Never `requests.get` elsewhere. The limiter orders all processes; user calls (default) go before `background=True`.
2. 1-3 requests the user waits for → call in the route (user priority). Examples: /statistics team lookup, head-to-head.
3. Many requests / per-player loops → Celery task on default queue with `ProgressReporter`; route writes `update_progress(task_id, 0, "Queued", 0)` then `.delay(...)`; client follows `/stream-progress/<id>` then `/results/<id>`. Example: players_statistics_task.
4. Data stale by clock → a `Job` in `jobs.JOBS` with `run` calling fetch with `background=True`; routes read the cache, fetch only on a cold cache; trigger with `queue_job_if_due(name)` (skip when TESTING).
- Cache TTL rule: Redis TTL for volatile data (key prefix `opendota:` / `liquipedia:`), SQLite for finished matches/immutable data. Cache TTL > job interval so the job refreshes before expiry. Cache errors 60 s (`{"error": ...}` value) to avoid request storms.

## Redis (db 0 = Celery broker/results; db 1 = everything else)
`progress:<task>` 1h, `progress-updates:<task>` pubsub, `results:<task>` 1h, `opendota:matches:<acc>:<days>` 1h, `opendota:rank:<acc>` 1d, `opendota:hero_stats:v2` 2h, `liquipedia:matches` 30min, `job:<name>` status JSON, `job:<name>:lock` 30min, `ratelimit:<name>:next|lock|day:YYYY-MM-DD`.

## SQLite (`instance/`)
- `d2ba.sqlite` = cache, deletable. Migrations `backend/migrations/*.sql`. Tables: pro_players, teams(team_id, rating, name, tag, logo_url, last_match_time), team_matches(+team_matches_sync TTL), match_players(match_id, player_slot, account_id, gpm, xpm), heroes, sync_state(name, synced_at).
- `predictions.sqlite` = user data, back up. Migrations `backend/migrations/predictions/`. Tables: team_snapshots (JSON `data`, UNIQUE team+date+days+last_match_time), predictions.
- Migrations: `YYYYMMDD_HHMMSS_name.sql`, auto-applied by `npm run dev`, no down migrations, split on `;` (no `;` in comments), add-only preferred. Every DB change needs Artem's approval: say so in the PR DB section.

## API (all in dota_bet_analyzer.py)
GET /version · GET /statistics?team=|team_id=&days= · GET /statistics/players?account_id= · GET /stream-progress/<task> (JSON lines) · GET /results/<task> · GET /teams/search · GET /matches · GET /heroes · GET /heroes/meta · GET /jobs · GET /jobs/stream (JSON lines, 2 s, 120 s max) · POST /jobs/<name>/run · POST /pro-players/sync, /teams/sync, /heroes/sync (legacy, unused by UI) · POST|GET /snapshots, GET /snapshots/<id> · POST|GET /predictions, GET|PUT|PATCH|DELETE /predictions/<id>, GET /predictions/<id>/head-to-head. Swagger: /api/swagger-ui.

## Recipes
- New endpoint: route in dota_bet_analyzer.py with `@bp.arguments(QuerySchema, location="query")`, `@bp.response(200, Schema)`, `@bp.alt_response(code, schema=ErrorSchema, description=...)`; body returns `jsonify(data), 200` (jsonify bypasses the schema, so the schema is docs only: keep fields in sync by hand); errors `return api_error(status, Errors.X, e, **details)`, add the code to `Errors` in helpers.py; validation errors are 422. Add `frontend/src/types.ts` shape, README Core Features line, tests for 200 + each error status.
- New cache job: fetch fn with `background` param using `get_json(..., background=background)`; `_run_x() -> str` in jobs.py (raise on empty data); add `Job(name, title, run, stale_after)` to JOBS; a sync_state row is written automatically. DataStatus UI lists it with no frontend change.
- New OpenDota-derived stat: first check if existing payloads already carry it (team matches, lineups, player matches) to avoid new requests; explorer SQL must stay short (`match_id IN (...)` works, joins on matches fail).
- New user task with progress: copy players_statistics_task pattern (ProgressReporter(task_id, total_steps), `.next()`, `.report()`, `.waiting()`, `.done()`, `.fail()`).
- New table/column: migration file + update the matching `*_schema.sql` + only columns current code reads.

## Frontend (`frontend/src`, React 19 + TS + Vite, no router, no state lib)
- `App.tsx`: tabs via URL hash (`#compare`, `#predictions`, `#predictions/<id>`, `#meta`), Compare flow (`handleCheck` → /statistics → `followProgress` per task → /results), header, raw JSON.
- `components/`: ComparisonTable (row config list: label, value, compare, better), InsightsTable, PredictionPanel/List/Detail, HeadToHeadTable, MatchesTables + seriesTable (paging 10), MetaTab (sortable), DataStatus (jobs stream), TeamAutocomplete, RowInfo (tooltip), BetOutcome.
- Helpers: `predictions.ts` (`requestJson` fetch helper: use it for new fetches; outcome/profit math), `progress.ts` (`followProgress`, `readLines`), `dataStatus.ts`, `format.ts` (COLOR_POSITIVE/NEGATIVE, value colours), `roster.tsx`, `series.ts`, `meta.ts`, `useTeamInput.ts`, `types.ts` (hand-written API shapes).
- Styles: `index.css` (global `a` style: all links white bold, underline on hover; no per-table link colours), `App.css` (everything else, dark purple gradient page), `TeamAutocomplete.css`. Colours are hard-coded literals today; reuse existing classes (`check-btn` white buttons, `.data-bar`, tag styles) instead of new colours.
- Tests: vitest + testing-library next to each file (`*.test.tsx`), fixtures in `src/test/`. App tests leak polling intervals: use unique task ids when counting fetches. When a label changes, assert the full new text.

## Tests (`tests/`, pytest)
- `conftest.py` autouse: resets app singleton; patches `backend.stats.resolve_roster` + `window_rating_change` (except test_rosters); patches `backend.jobs.queue_due_jobs_on_startup` (except test_jobs); no retry sleep; limiter `acquire` patched (except test_rate_limit). Fixtures `app` (temp instance with both DBs migrated), `client`.
- Mock HTTP at `backend.opendota.requests.get` or the module function (`backend.<module>.get_json`); mock Celery with `patch("backend.dota_bet_analyzer.players_statistics_task")`; Redis via `patch("backend.task_store.redis_client")` (also `backend.meta.`/`backend.matches.redis_client`, which are the same object imported).

## PR rules (from Artem)
Small PRs; plan first for big ones. Template `.github/pull_request_template.md`: Before/After, API (by endpoint + JSON path, one field per bullet), Backend, Frontend, DB, Other; empty section = "None."; no "no change" bullets; no player names. UI change → vitest tests in same PR. README Core Features for new features.

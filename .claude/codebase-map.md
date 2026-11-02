# Codebase map (for Claude; terse on purpose, read before exploring)

Update this file in the same PR when a module, endpoint, cache key, table, job or rule below changes.

## Run / check
- Backend tests: `python -m pytest tests/ -q` (~85 s without Redis: tests retry Redis in update_progress). Frontend: `cd frontend && npx vitest run`. Lint: `python -m pre_commit run --all-files`; frontend `npx eslint` has ~24 old errors, don't chase them.
- `npm run dev` = check Redis, apply migrations (scripts/init_d2ba_db.py), then 5 processes: flask :5000, celery worker (default queue), celery worker `-Q background`, celery beat, vite :5173 (proxies /api).
- Never edit `backend/VERSION`, `frontend/src/version.ts`, package versions: `.github/workflows/version.yml` bumps them on main.
- Tests never hit the network: everything is mocked (see Tests); a real HTTP request fails the test (`no_real_http`). OpenDota/Liquipedia are blocked from cloud sessions anyway.

## Backend (`backend/`, Flask + flask-smorest, one blueprint `bp` in dota_bet_analyzer.py, prefix /api)
| Module | Holds |
|---|---|
| `__init__.py` | create_app (singleton unless test_config), 422 handler → ErrorSchema, registers bp, queues due jobs at startup (not in TESTING) |
| `config.py` | Config from env: REDIS_HOST/PORT, OPENDOTA_MIN_INTERVAL 1.2, OPENDOTA_DAILY_LIMIT 1800, LIQUIPEDIA_MIN_INTERVAL 30 |
| `dota_bet_analyzer.py` | ALL routes (~1300 lines) + `players_statistics_task` (Celery, default queue) + stream generators |
| `celery_app.py` | `celery`, BACKGROUND_QUEUE="background", beat: check_due_jobs_task every 60 s |
| `opendota.py` | ONLY OpenDota HTTP: `get_json(path, params, timeout, on_wait, background)` → JSON or raises `OpenDotaError(status, code, message)`; `opendota_get` raw; retry 403/429/timeouts; `OPENDOTA_LIMITER`; `is_radiant(slot)` |
| `rate_limit.py` | `RateLimiter` (Redis slot+lock+UTC day counter, shared by all processes), `DailyLimitReached`, `report_waits(cb)` ctx |
| `jobs.py` | Cache job registry `JOBS` (pro_players 24h, heroes 7d, teams 24h, hero_meta 1h, matches 10min), `queue_job(name, full)`, `queue_job_if_due`, `run_job`, optional `Job.run_full` (teams), status in Redis, last success in `sync_state` |
| `cache.py` | The app's ONE Redis db1 client `redis_client` (jobs, meta, matches, task_store, RateLimiter default use it); `cache_get`, `cache_set`, `cached_json(key, ttl, fetch, error_ttl=None, use=None)`: with error_ttl a ConnectionError/ValueError from fetch is cached as `{"error": msg}` and raised again as ConnectionError; `use(value)` False refetches |
| `task_store.py` | (uses cache.redis_client) `update_progress`, `start_task(task, team_id=None, **kwargs)` → (task_id, celery_id) with ids `task_<team_id>_<uuid hex>` / `task_<uuid hex>`, `ProgressReporter`, `store_results`/`get_results`, `get_matches_cached` (1h), `get_rank_cached` (1d), progress pub/sub |
| `stats.py` | Compare: `compute_statistics` (sync, in request) → per team explorer lookup, team info, roster, rating change, starts `players_statistics_task`; RankTally; `get_matches`, `get_rank` (both raise OpenDotaError on a failed request, so errors are never cached), `get_team_matches_summary` |
| `models.py` | pydantic data models (imports only helpers + opendota, so no cycles): Player, FarmStats, LeagueForm, TeamRoster, TeamStats, MatchStats, StatsResponse, MatchesSummary; new shared models go here |
| `rosters.py` | `resolve_roster`, `classify_roster` (core rule), `get_team_league_matches` (SQLite, 2h TTL), `get_match_lineups` (SQLite forever, explorer batches of 20; lineups under 10 players in Redis 1d), `window_start`, `DAY_SECONDS` |
| `ratings.py` | `window_rating_change` Elo back-calc, no requests |
| `db.py` | The ONLY SQLite connections: `get_cache_db()` (instance/d2ba.sqlite, WAL mode), `get_user_db()` (instance/predictions.sqlite, foreign keys on, rollback journal), both 15 s busy timeout, per app context, closed on teardown |
| `pro_players.py` | pro players fetch/store, `get_players_by_team`, teams fetch/store (full /teams pages) |
| `teams_sync.py` | `run_teams_sync(full)`: incremental 2 explorer queries, full ~22 pages; only the `teams` job calls it |
| `heroes.py` | /constants/heroes → `heroes` table, `list_heroes` |
| `meta.py` | /heroStats → Redis `opendota:hero_stats:v2` (2h, errors 60s), `MetaParams`, `compute_meta`, `get_meta` |
| `matches.py` | Liquipedia parse → Redis `liquipedia:matches` (30min, errors 60s), `LIQUIPEDIA_LIMITER`, `TeamMatcher` (name → teams table), own `requests.get` (only allowed exception) |
| `head_to_head.py` | from cached team matches, 0-1 requests |
| `snapshots.py`, `predictions.py` | user data in predictions.sqlite via `db.get_user_db()` |
| `helpers.py` | `Errors` registry (ErrorDefinition code+message), `ApiError`, `api_error(status, Errors.X, exc=None, **details)` → (Response, status), explorer SQL builder, `ExplorerTeam` |
| `schemas.py` | marshmallow schemas; `pydantic_to_marshmallow` derives ErrorSchema/TeamStatsSchema/StatsResponseSchema/PlayerSchema from pydantic |
| `d2ba_schema.sql`, `predictions_schema.sql` | docs only, not applied; `tests/test_migrations_match_schema.py` fails when they differ from the migrations |

## Request paths (queueing rules; pick one for new work)
1. Every HTTP call → `opendota.get_json` (Liquipedia: `matches.fetch_matches_from_liquipedia`). Never `requests.get` elsewhere (`tests/test_network_guard.py` fails if another backend module imports an HTTP library). The limiter orders all processes; user calls (default) go before `background=True`.
2. 1-3 requests the user waits for → call in the route (user priority). Examples: /statistics team lookup, head-to-head.
3. Many requests / per-player loops → Celery task on default queue with `ProgressReporter`; route calls `task_store.start_task(task, team_id=..., **kwargs)` (writes "Queued", then `.delay`); client follows `/stream-progress/<id>` then `/results/<id>`. Example: players_statistics_task.
4. Data stale by clock → a `Job` in `jobs.JOBS` with `run` calling fetch with `background=True`; routes read the cache, fetch only on a cold cache; trigger with `queue_job_if_due(name)` (skip when TESTING).
- Cache TTL rule: Redis TTL for volatile data (key prefix `opendota:` / `liquipedia:`), SQLite for finished matches/immutable data. Cache TTL > job interval so the job refreshes before expiry. Cache errors 60 s (`{"error": ...}` value) to avoid request storms. New Redis cache → `cache.cached_json`, never a new Redis client.

## Redis (db 0 = Celery broker/results; db 1 = everything else)
`progress:<task>` 1h, `progress-updates:<task>` pubsub, `results:<task>` 1h, `opendota:matches:<acc>:<days>` 1h, `opendota:rank:<acc>` 1d, `opendota:hero_stats:v2` 2h, `opendota:short_lineup:<match>` 1d, `liquipedia:matches` 30min, `job:<name>` status JSON, `job:<name>:lock` 30min, `ratelimit:<name>:next|lock|day:YYYY-MM-DD`.

## SQLite (`instance/`)
- `d2ba.sqlite` = cache, deletable (WAL: delete with its -wal/-shm files). Migrations `backend/migrations/*.sql`. Tables: pro_players, teams(team_id, rating, name, tag, logo_url, last_match_time), team_matches(+team_matches_sync TTL), match_players(match_id, player_slot, account_id, gpm, xpm), heroes, sync_state(name, synced_at).
- `predictions.sqlite` = user data, back up. Migrations `backend/migrations/predictions/`. Tables: team_snapshots (JSON `data`, UNIQUE team+date+days+last_match_time), predictions.
- Migrations: `YYYYMMDD_HHMMSS_name.sql`, auto-applied by `npm run dev`, no down migrations, split on `;` (no `;` in comments), add-only preferred. Every DB change needs Artem's approval: say so in the PR DB section.

## API (all in dota_bet_analyzer.py)
GET /version · GET /statistics?team=|team_id=&days= · GET /statistics/players?account_id= · GET /stream-progress/<task> (JSON lines) · GET /results/<task> · GET /teams/search · GET /matches · GET /heroes · GET /heroes/meta · GET /jobs · GET /jobs/stream (JSON lines, 2 s, 120 s max) · POST /jobs/<name>/run (`?full=true` teams only) · POST|GET /snapshots, GET /snapshots/<id> · POST|GET /predictions, GET|PUT|PATCH|DELETE /predictions/<id>, GET /predictions/<id>/head-to-head. Swagger: /api/swagger-ui.

## Recipes
- New endpoint: route in dota_bet_analyzer.py with `@bp.arguments(QuerySchema, location="query")`, `@bp.response(200, Schema)`, `@bp.alt_response(code, schema=ErrorSchema, description=...)`; body returns `jsonify(data), 200` (jsonify bypasses the schema, so the schema is docs only: keep fields in sync by hand); errors `return api_error(status, Errors.X, e, **details)`, add the code to `Errors` in helpers.py; validation errors are 422. Add `frontend/src/types.ts` shape, README Core Features line, tests for 200 + each error status.
- New cache job: fetch fn with `background` param using `get_json(..., background=background)`; `_run_x() -> str` in jobs.py (raise on empty data); add `Job(name, title, run, stale_after)` to JOBS; a sync_state row is written automatically. DataStatus UI lists it with no frontend change.
- New OpenDota-derived stat: first check if existing payloads already carry it (team matches, lineups, player matches) to avoid new requests; explorer SQL must stay short (`match_id IN (...)` works, joins on matches fail).
- New user task with progress: copy players_statistics_task pattern (ProgressReporter(task_id, total_steps), `.next()`, `.report()`, `.waiting()`, `.done()`, `.fail()`).
- New table/column: migration file + update the matching `*_schema.sql` + only columns current code reads.

## Frontend (`frontend/src`, React 19 + TS + Vite, no router, no state lib)
- `App.tsx`: tabs via URL hash (`#compare`, `#predictions`, `#predictions/<id>`, `#meta`), Compare flow (`handleCheck` → /statistics → `followProgress` per task → /results), header, raw JSON.
- `components/`: ComparisonTable (row config list: label, value, compare, better), InsightsTable, PredictionPanel/List/Detail, HeadToHeadTable, MatchesTables + seriesTable (paging 10), MetaTab (sortable), DataStatus (jobs stream), TeamAutocomplete, RowInfo (tooltip), BetOutcome, Bar (one bar for Compare progress, Data status, Meta cells).
- Helpers: `api.ts` (`requestJson`, `postJson`/`putJson`/`patchJson`: every JSON fetch goes through them, they throw with the backend `message`; only the streams in progress.ts/dataStatus.ts and the /version retry use raw `fetch`), `predictions.ts` (outcome/profit math), `progress.ts` (`followProgress`, `readLines`), `dataStatus.ts`, `format.ts` (CELL_POSITIVE/NEGATIVE = `cell-pos`/`cell-neg` classes for better/worse cells), `roster.tsx`, `series.ts`, `meta.ts`, `useTeamInput.ts`, `types.ts` (hand-written API shapes).
- Styles: `index.css` (colour tokens in `:root`: `--accent`, `--pos`/`--neg`, `--pos-text`/`--neg-text`, `--error`, `--gold`, `--surface-1..4`, `--shade-1..4`, `--line`, `--border`, `--menu-bg`...; global `a` style: all links white bold, underline on hover; no per-table link colours; dark only), `App.css` (everything else, dark purple gradient page; colours only via `var(--token)`), `TeamAutocomplete.css` (team search, dark dropdown on `--menu-bg`, input uses the global `input` style). New colours: add a token in index.css, never a literal (`src/colourTokens.test.ts` fails on hex/rgb/hsl in any other .css/.tsx); reuse existing classes (`check-btn` white buttons, tag styles) and components (`Bar` for every horizontal bar: `value`, `max`, `tone`, `size`, `label`).
- Tests: vitest + testing-library next to each file (`*.test.tsx`), fixtures in `src/test/`. App tests leak polling intervals: use unique task ids when counting fetches. When a label changes, assert the full new text.

## Tests (`tests/`, pytest)
- `conftest.py` autouse: resets app singleton; patches `backend.stats.resolve_roster` + `window_rating_change` (except test_rosters); patches `backend.jobs.queue_due_jobs_on_startup` (except test_jobs); no retry sleep; limiter `acquire` patched (except test_rate_limit); `no_real_http` blocks real requests and fails the test at teardown. Fixtures `app` (temp instance with both DBs migrated), `client`.
- Mock HTTP at `backend.opendota.requests.get` or the module function (`backend.<module>.get_json`); mock Celery with `patch("backend.dota_bet_analyzer.players_statistics_task")`; Redis only via `patch("backend.cache.redis_client")`.

## PR rules (from Artem)
Small PRs; plan first for big ones. Template `.github/pull_request_template.md`: Before/After, API (by endpoint + JSON path, one field per bullet), Backend, Frontend, DB, Other; empty section = "None."; no "no change" bullets; no player names. UI change → vitest tests in same PR. README Core Features for new features.

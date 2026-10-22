-- Schema for predictions.sqlite - the user's own data (back it up; d2ba.sqlite is only a cache)
-- Applied by migrations in backend/migrations/predictions/

-- Team statistics snapshot: what the Compare page showed for a team.
-- One row per team + UTC day (YYYY-MM-DD) + days window + latest league match (unix seconds, 0 = none).
-- saving the same key again refreshes taken_at, app_version and data.
-- data is JSON: {"team": teams[] entry of /api/statistics, "summary": /api/results summary or null,
-- "players": [{"account_id", "rank", "match_count"}]}
CREATE TABLE IF NOT EXISTS team_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL,
    snapshot_date TEXT NOT NULL,
    days INTEGER NOT NULL,
    last_match_time INTEGER NOT NULL DEFAULT 0,
    taken_at INTEGER NOT NULL,
    app_version TEXT NOT NULL,
    data TEXT NOT NULL,
    UNIQUE (team_id, snapshot_date, days, last_match_time)
);

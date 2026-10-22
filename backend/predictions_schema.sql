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

-- Prediction: a series-win bet (or a prediction without a bet, bet_team NULL) made from two team snapshots.
-- Odds, best_of, bet_team, stake and comment are locked after saving, a snapshot used here is no longer refreshed.
-- best_of NULL = series format unknown (n/a).
-- team1_maps_won / team2_maps_won: the actual result (bo3 2-1 = 2 and 1), NULL until reviewed.
-- Winner and bet outcome are computed from these, not stored.
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at INTEGER NOT NULL,
    team1_snapshot_id INTEGER NOT NULL REFERENCES team_snapshots(snapshot_id),
    team2_snapshot_id INTEGER NOT NULL REFERENCES team_snapshots(snapshot_id),
    team1_odds REAL NOT NULL,
    team2_odds REAL NOT NULL,
    best_of INTEGER CHECK (best_of IN (1, 2, 3, 5)),
    bet_team INTEGER CHECK (bet_team IN (1, 2)),
    stake REAL,
    comment TEXT NOT NULL DEFAULT '',
    team1_maps_won INTEGER,
    team2_maps_won INTEGER,
    review_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_predictions_created ON predictions(created_at);

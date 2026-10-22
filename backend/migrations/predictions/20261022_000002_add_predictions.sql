-- Migration: 20261022_000002_add_predictions.sql
-- Description: Predictions (series-win bets) that point at the two team snapshots they were made from
-- Created: 2026-10-22
-- Dependencies: 20261022_000001_add_team_snapshots.sql

-- best_of NULL = series format unknown. Odds, bet and comment are locked after saving. The result (maps won) and review_note are filled in the review
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

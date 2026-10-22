-- Migration: 20261022_000001_add_team_snapshots.sql
-- Description: Team statistics snapshots (what the Compare page showed for a team), first table of predictions.sqlite
-- Created: 2026-10-22

-- One row per team + UTC day + days window + latest league match (saving the same key again refreshes it)
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

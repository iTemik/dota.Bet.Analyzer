-- Migration: 20261018_000001_add_roster_cache.sql
-- Description: Cache tables for team league matches and match lineups used to resolve real team rosters
-- Created: 2026-10-18
-- Dependencies: add_last_match_time_to_teams

-- League matches of a team as returned by /teams/{team_id}/matches
CREATE TABLE IF NOT EXISTS team_matches (
    team_id INTEGER NOT NULL,
    match_id INTEGER NOT NULL,
    start_time INTEGER NOT NULL,
    leagueid INTEGER,
    league_name TEXT,
    radiant BOOLEAN NOT NULL,
    radiant_win BOOLEAN,
    opposing_team_id INTEGER,
    opposing_team_name TEXT,
    PRIMARY KEY (team_id, match_id)
);

CREATE INDEX IF NOT EXISTS idx_team_matches_team_time ON team_matches(team_id, start_time);

-- When /teams/{team_id}/matches was last fetched (cache TTL)
CREATE TABLE IF NOT EXISTS team_matches_sync (
    team_id INTEGER PRIMARY KEY,
    fetched_at INTEGER NOT NULL
);

-- Players of a finished match (never changes, so it is cached forever)
CREATE TABLE IF NOT EXISTS match_players (
    match_id INTEGER NOT NULL,
    player_slot INTEGER NOT NULL,
    account_id INTEGER,
    PRIMARY KEY (match_id, player_slot)
);

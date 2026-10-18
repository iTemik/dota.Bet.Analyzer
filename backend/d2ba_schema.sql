-- Schema for d2ba.sqlite - Dota 2 Bet Analyzer database
-- Pro players data from OpenDota API
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS pro_players (
    account_id INTEGER PRIMARY KEY,
    steamid TEXT,
    profileurl TEXT,
    personaname TEXT,
    name TEXT,
    fantasy_role INTEGER,
    team_id INTEGER,
    team_name TEXT,
    team_tag TEXT,
    is_pro BOOLEAN
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_pro_players_name ON pro_players(name);
CREATE INDEX IF NOT EXISTS idx_pro_players_team_id ON pro_players(team_id);

-- Teams data from OpenDota API
CREATE TABLE IF NOT EXISTS teams (
    team_id INTEGER PRIMARY KEY,
    rating REAL,
    name TEXT,
    tag TEXT,
    logo_url TEXT,
    last_match_time INTEGER
);

-- Create indexes for teams
CREATE INDEX IF NOT EXISTS idx_teams_name ON teams(name);
CREATE INDEX IF NOT EXISTS idx_teams_tag ON teams(tag);

-- League matches of a team as returned by /teams/{team_id}/matches
CREATE TABLE IF NOT EXISTS team_matches (
    team_id INTEGER NOT NULL,
    match_id INTEGER NOT NULL,
    start_time INTEGER NOT NULL,
    leagueid INTEGER,
    radiant BOOLEAN NOT NULL,
    radiant_win BOOLEAN,
    opposing_team_id INTEGER,
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

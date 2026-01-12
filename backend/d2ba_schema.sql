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

-- Migration: 20261022_000002_add_sync_state.sql
-- Description: Time of the last successful sync of an OpenDota list (teams), used to re-sync after 30 days
-- Created: 2026-10-22
-- Dependencies: add_heroes

CREATE TABLE IF NOT EXISTS sync_state (
    name TEXT PRIMARY KEY,
    synced_at INTEGER NOT NULL
);

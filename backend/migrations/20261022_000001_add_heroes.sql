-- Migration: 20261022_000001_add_heroes.sql
-- Description: Hero list from OpenDota /constants/heroes (id, names, icon URL)
-- Created: 2026-10-22
-- Dependencies: add_roster_cache

CREATE TABLE IF NOT EXISTS heroes (
    hero_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    localized_name TEXT NOT NULL,
    icon TEXT NOT NULL
);

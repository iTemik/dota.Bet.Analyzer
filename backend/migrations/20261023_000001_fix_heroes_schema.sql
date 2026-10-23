-- Migration: 20261023_000001_fix_heroes_schema.sql
-- Description: Fix heroes table to use hero_id instead of id for compatibility with backend code
-- Created: 2026-10-23
-- Issue: The legacy opendota_schema.sql created a heroes table with 'id' as the primary key,
--        but the backend code (backend/heroes.py) expects 'hero_id' column. This caused
--        "table heroes has no column named hero_id" errors during sync.

-- Drop the incorrectly-schemed heroes table from opendota_schema.sql
DROP TABLE IF EXISTS heroes;

-- Create the correct heroes table that matches backend/heroes.py expectations
CREATE TABLE heroes (
    hero_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    localized_name TEXT NOT NULL,
    icon TEXT NOT NULL
);

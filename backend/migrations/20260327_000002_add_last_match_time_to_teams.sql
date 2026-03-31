-- Migration: 20260327_000002_add_last_match_time_to_teams.sql
-- Description: Add last_match_time column to teams table for tracking recent match activity
-- Created: 2026-03-27
-- Dependencies: initial_schema
-- Status: Applied

-- UP: Add last_match_time column; idempotency is handled by the migration runner
-- The runner treats duplicate-column errors as a successful no-op when the column already exists.
ALTER TABLE teams ADD COLUMN last_match_time INTEGER;

-- Note: This migration relies on the migration runner to ignore the
-- "duplicate column name: last_match_time" error if the column already exists.

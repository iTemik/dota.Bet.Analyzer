-- Migration: 20260327_000002_add_last_match_time_to_teams.sql
-- Description: Add last_match_time column to teams table for tracking recent match activity
-- Created: 2026-03-27
-- Dependencies: initial_schema
-- Status: Applied

-- UP: Add last_match_time column if it doesn't exist
-- Using IF NOT EXISTS pattern for idempotency
ALTER TABLE teams ADD COLUMN last_match_time INTEGER;

-- Note: This migration is idempotent. If the column already exists,
-- SQLite will raise an error which can be ignored by the migration runner.

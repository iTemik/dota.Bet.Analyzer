-- Migration: 20261104_000001_add_lineup_hero.sql
-- Description: Keep the picked hero with cached lineups (team and player league hero pools)
-- Created: 2026-11-04
-- Dependencies: 20261029_000001_add_lineup_stats_and_duration
-- match_players is a cache. Cached lineups have no hero, so they are cleared and fetched again once (one explorer
-- query per 20 matches).

ALTER TABLE match_players ADD COLUMN hero_id INTEGER;
DELETE FROM match_players;

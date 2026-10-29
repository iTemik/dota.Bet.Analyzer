-- Migration: 20261029_000001_add_lineup_stats_and_duration.sql
-- Description: Keep player match stats with cached lineups (carry and mid medians) and match length with team matches
-- Created: 2026-10-29
-- Dependencies: 20261018_000001_add_roster_cache
-- Both tables are caches. Cached lineups have no stats, so they are cleared and fetched again once (one explorer
-- query per 20 matches). Team matches are marked stale so they are fetched again with the duration on the next use.

ALTER TABLE match_players ADD COLUMN gold_per_min INTEGER;
ALTER TABLE match_players ADD COLUMN xp_per_min INTEGER;
ALTER TABLE match_players ADD COLUMN last_hits INTEGER;
ALTER TABLE match_players ADD COLUMN lane INTEGER;
DELETE FROM match_players;

ALTER TABLE team_matches ADD COLUMN duration INTEGER;
DELETE FROM team_matches_sync;

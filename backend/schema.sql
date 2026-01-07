-- Auto-generated SQLite schema from backend/schema.txt which is the response of opendota api: https://api.opendota.com/api/schema
-- Generated: primary keys inferred where safe, timestamps stored as INTEGER (Unix epoch)
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS "aliases" (
  "account_id" INTEGER,
  "personaname" TEXT,
  "name_since" INTEGER
);

CREATE TABLE IF NOT EXISTS "api_key_usage" (
  "account_id" INTEGER,
  "customer_id" TEXT,
  "api_key" TEXT,
  "usage_count" INTEGER,
  "ip" TEXT,
  "timestamp" INTEGER
);

CREATE TABLE IF NOT EXISTS "api_keys" (
  "account_id" INTEGER,
  "api_key" TEXT,
  "customer_id" TEXT,
  "subscription_id" TEXT,
  "is_canceled" BOOLEAN
);

CREATE TABLE IF NOT EXISTS "competitive_rank" (
  "account_id" INTEGER,
  "rating" INTEGER
);

CREATE TABLE IF NOT EXISTS "cosmetics" (
  "item_id" INTEGER,
  "name" TEXT,
  "prefab" TEXT,
  "creation_date" INTEGER,
  "image_inventory" TEXT,
  "image_path" TEXT,
  "item_description" TEXT,
  "item_name" TEXT,
  "item_rarity" TEXT,
  "item_type_name" TEXT,
  "used_by_heroes" TEXT
);

CREATE TABLE IF NOT EXISTS "hero_ranking" (
  "account_id" INTEGER,
  "hero_id" INTEGER,
  "score" REAL
);

CREATE TABLE IF NOT EXISTS "heroes" (
  "id" INTEGER PRIMARY KEY,
  "name" TEXT,
  "localized_name" TEXT,
  "primary_attr" TEXT,
  "attack_type" TEXT,
  "roles" JSON,
  "legs" INTEGER
);

CREATE TABLE IF NOT EXISTS "insert_queue" (
  "match_seq_num" INTEGER,
  "data" JSON,
  "processed" BOOLEAN
);

CREATE TABLE IF NOT EXISTS "items" (
  "id" INTEGER PRIMARY KEY,
  "name" TEXT,
  "cost" INTEGER,
  "secret_shop" INTEGER,
  "side_shop" INTEGER,
  "recipe" INTEGER,
  "localized_name" TEXT
);

CREATE TABLE IF NOT EXISTS "leaderboard_rank" (
  "account_id" INTEGER,
  "rating" INTEGER
);

CREATE TABLE IF NOT EXISTS "league_match" (
  "leagueid" INTEGER,
  "match_id" INTEGER
);

CREATE TABLE IF NOT EXISTS "leagues" (
  "leagueid" INTEGER,
  "ticket" TEXT,
  "banner" TEXT,
  "tier" TEXT,
  "name" TEXT
);

CREATE TABLE IF NOT EXISTS "match_patch" (
  "match_id" INTEGER,
  "patch" TEXT
);

CREATE TABLE IF NOT EXISTS "matches" (
  "match_id" INTEGER,
  "match_seq_num" INTEGER,
  "radiant_win" BOOLEAN,
  "start_time" INTEGER,
  "duration" INTEGER,
  "tower_status_radiant" INTEGER,
  "tower_status_dire" INTEGER,
  "barracks_status_radiant" INTEGER,
  "barracks_status_dire" INTEGER,
  "cluster" INTEGER,
  "first_blood_time" INTEGER,
  "lobby_type" INTEGER,
  "human_players" INTEGER,
  "leagueid" INTEGER,
  "positive_votes" INTEGER,
  "negative_votes" INTEGER,
  "game_mode" INTEGER,
  "engine" INTEGER,
  "picks_bans" JSON,
  "radiant_team_id" INTEGER,
  "dire_team_id" INTEGER,
  "radiant_team_name" TEXT,
  "dire_team_name" TEXT,
  "radiant_team_complete" INTEGER,
  "dire_team_complete" INTEGER,
  "radiant_captain" INTEGER,
  "dire_captain" INTEGER,
  "chat" JSON,
  "objectives" JSON,
  "radiant_gold_adv" JSON,
  "radiant_xp_adv" JSON,
  "teamfights" JSON,
  "version" INTEGER,
  "cosmetics" JSON,
  "radiant_score" INTEGER,
  "dire_score" INTEGER,
  "draft_timings" JSON,
  "series_id" INTEGER,
  "series_type" INTEGER,
  "replay_salt" INTEGER
);

CREATE TABLE IF NOT EXISTS "notable_players" (
  "account_id" INTEGER,
  "name" TEXT,
  "country_code" TEXT,
  "fantasy_role" INTEGER,
  "team_id" INTEGER,
  "team_name" TEXT,
  "team_tag" TEXT,
  "is_locked" BOOLEAN,
  "is_pro" BOOLEAN,
  "locked_until" INTEGER
);

CREATE TABLE IF NOT EXISTS "parsed_matches" (
  "match_id" INTEGER,
  "is_archived" BOOLEAN
);

CREATE TABLE IF NOT EXISTS "picks_bans" (
  "match_id" INTEGER,
  "is_pick" BOOLEAN,
  "hero_id" INTEGER,
  "team" INTEGER,
  "ord" INTEGER
);

CREATE TABLE IF NOT EXISTS "player_computed_mmr" (
  "account_id" INTEGER,
  "computed_mmr" REAL,
  "delta" REAL,
  "match_id" INTEGER
);

CREATE TABLE IF NOT EXISTS "player_computed_mmr_turbo" (
  "account_id" INTEGER,
  "computed_mmr" REAL,
  "delta" REAL,
  "match_id" INTEGER
);

CREATE TABLE IF NOT EXISTS "player_match_history" (
  "account_id" INTEGER,
  "match_id" INTEGER,
  "player_slot" INTEGER,
  "retries" INTEGER
);

CREATE TABLE IF NOT EXISTS "player_matches" (
  "match_id" INTEGER,
  "account_id" INTEGER,
  "player_slot" INTEGER,
  "hero_id" INTEGER,
  "item_0" INTEGER,
  "item_1" INTEGER,
  "item_2" INTEGER,
  "item_3" INTEGER,
  "item_4" INTEGER,
  "item_5" INTEGER,
  "kills" INTEGER,
  "deaths" INTEGER,
  "assists" INTEGER,
  "leaver_status" INTEGER,
  "gold" INTEGER,
  "last_hits" INTEGER,
  "denies" INTEGER,
  "gold_per_min" INTEGER,
  "xp_per_min" INTEGER,
  "gold_spent" INTEGER,
  "hero_damage" INTEGER,
  "tower_damage" INTEGER,
  "hero_healing" INTEGER,
  "level" INTEGER,
  "additional_units" JSON,
  "stuns" REAL,
  "max_hero_hit" JSON,
  "times" JSON,
  "gold_t" JSON,
  "lh_t" JSON,
  "xp_t" JSON,
  "obs_log" JSON,
  "sen_log" JSON,
  "purchase_log" JSON,
  "kills_log" JSON,
  "buyback_log" JSON,
  "lane_pos" JSON,
  "obs" JSON,
  "sen" JSON,
  "actions" JSON,
  "pings" JSON,
  "purchase" JSON,
  "gold_reasons" JSON,
  "xp_reasons" JSON,
  "killed" JSON,
  "item_uses" JSON,
  "ability_uses" JSON,
  "hero_hits" JSON,
  "damage" JSON,
  "damage_taken" JSON,
  "damage_inflictor" JSON,
  "runes" JSON,
  "killed_by" JSON,
  "kill_streaks" JSON,
  "multi_kills" JSON,
  "life_state" JSON,
  "damage_inflictor_received" JSON,
  "obs_placed" INTEGER,
  "sen_placed" INTEGER,
  "creeps_stacked" INTEGER,
  "camps_stacked" INTEGER,
  "rune_pickups" INTEGER,
  "obs_left_log" JSON,
  "sen_left_log" JSON,
  "ability_upgrades_arr" JSON,
  "party_id" INTEGER,
  "permanent_buffs" JSON,
  "backpack_0" INTEGER,
  "backpack_1" INTEGER,
  "backpack_2" INTEGER,
  "runes_log" JSON,
  "lane" INTEGER,
  "lane_role" INTEGER,
  "is_roaming" BOOLEAN,
  "firstblood_claimed" INTEGER,
  "teamfight_participation" REAL,
  "towers_killed" INTEGER,
  "roshans_killed" INTEGER,
  "observers_placed" INTEGER,
  "party_size" INTEGER,
  "ability_targets" JSON,
  "damage_targets" JSON,
  "dn_t" JSON,
  "connection_log" JSON,
  "backpack_3" INTEGER,
  "item_neutral" INTEGER,
  "net_worth" INTEGER,
  "hero_variant" INTEGER,
  "neutral_tokens_log" JSON,
  "neutral_item_history" JSON
);

CREATE TABLE IF NOT EXISTS "player_ratings" (
  "account_id" INTEGER,
  "match_id" INTEGER,
  "solo_competitive_rank" INTEGER,
  "competitive_rank" INTEGER,
  "time" INTEGER
);

CREATE TABLE IF NOT EXISTS "players" (
  "account_id" INTEGER,
  "steamid" TEXT,
  "avatar" TEXT,
  "avatarmedium" TEXT,
  "avatarfull" TEXT,
  "profileurl" TEXT,
  "personaname" TEXT,
  "last_login" INTEGER,
  "full_history_time" INTEGER,
  "cheese" INTEGER,
  "fh_unavailable" BOOLEAN,
  "loccountrycode" TEXT,
  "last_match_time" INTEGER,
  "plus" BOOLEAN,
  "profile_time" INTEGER,
  "rank_tier_time" INTEGER
);

CREATE TABLE IF NOT EXISTS "public_matches" (
  "match_id" INTEGER,
  "match_seq_num" INTEGER,
  "radiant_win" BOOLEAN,
  "start_time" INTEGER,
  "duration" INTEGER,
  "lobby_type" INTEGER,
  "game_mode" INTEGER,
  "avg_rank_tier" REAL,
  "num_rank_tier" INTEGER,
  "cluster" INTEGER,
  "radiant_team" JSON,
  "dire_team" JSON
);

CREATE TABLE IF NOT EXISTS "queue" (
  "id" INTEGER PRIMARY KEY,
  "type" TEXT,
  "timestamp" INTEGER,
  "attempts" INTEGER,
  "data" JSON,
  "next_attempt_time" INTEGER,
  "priority" INTEGER,
  "job_key" TEXT
);

CREATE TABLE IF NOT EXISTS "rank_tier" (
  "account_id" INTEGER,
  "rating" INTEGER
);

CREATE TABLE IF NOT EXISTS "rank_tier_2019_1" (
  "account_id" INTEGER,
  "rating" INTEGER
);

CREATE TABLE IF NOT EXISTS "rank_tier_history" (
  "account_id" INTEGER,
  "time" INTEGER,
  "rank_tier" INTEGER
);

CREATE TABLE IF NOT EXISTS "rating_queue" (
  "match_seq_num" INTEGER,
  "match_id" INTEGER,
  "radiant_win" BOOLEAN,
  "game_mode" INTEGER
);

CREATE TABLE IF NOT EXISTS "scenarios" (
  "hero_id" INTEGER,
  "item" TEXT,
  "time" INTEGER,
  "lane_role" INTEGER,
  "games" INTEGER,
  "wins" INTEGER,
  "epoch_week" INTEGER
);

CREATE TABLE IF NOT EXISTS "solo_competitive_rank" (
  "account_id" INTEGER,
  "rating" INTEGER
);

CREATE TABLE IF NOT EXISTS "subscriber" (
  "account_id" INTEGER,
  "customer_id" TEXT,
  "status" TEXT
);

CREATE TABLE IF NOT EXISTS "subscriptions" (
  "account_id" INTEGER,
  "customer_id" TEXT,
  "amount" INTEGER,
  "active_until" INTEGER
);

CREATE TABLE IF NOT EXISTS "team_match" (
  "team_id" INTEGER,
  "match_id" INTEGER,
  "radiant" BOOLEAN
);

CREATE TABLE IF NOT EXISTS "team_rating" (
  "team_id" INTEGER,
  "rating" REAL,
  "wins" INTEGER,
  "losses" INTEGER,
  "last_match_time" INTEGER,
  "delta" REAL,
  "match_id" INTEGER
);

CREATE TABLE IF NOT EXISTS "team_scenarios" (
  "scenario" TEXT,
  "is_radiant" BOOLEAN,
  "region" INTEGER,
  "games" INTEGER,
  "wins" INTEGER,
  "epoch_week" INTEGER
);

CREATE TABLE IF NOT EXISTS "teams" (
  "team_id" INTEGER PRIMARY KEY,
  "name" TEXT,
  "tag" TEXT,
  "logo_url" TEXT
);

CREATE TABLE IF NOT EXISTS "user_usage" (
  "account_id" INTEGER,
  "ip" TEXT,
  "usage_count" INTEGER,
  "timestamp" INTEGER
);

CREATE TABLE IF NOT EXISTS "webhooks" (
  "hook_id" TEXT PRIMARY KEY,
  "account_id" INTEGER,
  "url" TEXT,
  "subscriptions" JSON
);

CREATE INDEX IF NOT EXISTS "idx_aliases_account_id" ON "aliases" ("account_id");
CREATE INDEX IF NOT EXISTS "idx_api_key_usage_account_id" ON "api_key_usage" ("account_id");
CREATE INDEX IF NOT EXISTS "idx_api_key_usage_api_key" ON "api_key_usage" ("api_key");
CREATE INDEX IF NOT EXISTS "idx_api_keys_account_id" ON "api_keys" ("account_id");
CREATE INDEX IF NOT EXISTS "idx_api_keys_api_key" ON "api_keys" ("api_key");
CREATE INDEX IF NOT EXISTS "idx_competitive_rank_account_id" ON "competitive_rank" ("account_id");
CREATE INDEX IF NOT EXISTS "idx_hero_ranking_account_id" ON "hero_ranking" ("account_id");
CREATE INDEX IF NOT EXISTS "idx_insert_queue_match_seq_num" ON "insert_queue" ("match_seq_num");
CREATE INDEX IF NOT EXISTS "idx_leaderboard_rank_account_id" ON "leaderboard_rank" ("account_id");
CREATE INDEX IF NOT EXISTS "idx_league_match_leagueid" ON "league_match" ("leagueid");
CREATE INDEX IF NOT EXISTS "idx_league_match_match_id" ON "league_match" ("match_id");
CREATE INDEX IF NOT EXISTS "idx_leagues_leagueid" ON "leagues" ("leagueid");
CREATE INDEX IF NOT EXISTS "idx_match_patch_match_id" ON "match_patch" ("match_id");
CREATE INDEX IF NOT EXISTS "idx_matches_match_id" ON "matches" ("match_id");
CREATE INDEX IF NOT EXISTS "idx_matches_match_seq_num" ON "matches" ("match_seq_num");
CREATE INDEX IF NOT EXISTS "idx_matches_leagueid" ON "matches" ("leagueid");
CREATE INDEX IF NOT EXISTS "idx_notable_players_account_id" ON "notable_players" ("account_id");
CREATE INDEX IF NOT EXISTS "idx_notable_players_team_id" ON "notable_players" ("team_id");
CREATE INDEX IF NOT EXISTS "idx_parsed_matches_match_id" ON "parsed_matches" ("match_id");
CREATE INDEX IF NOT EXISTS "idx_picks_bans_match_id" ON "picks_bans" ("match_id");
CREATE INDEX IF NOT EXISTS "idx_player_computed_mmr_account_id" ON "player_computed_mmr" ("account_id");
CREATE INDEX IF NOT EXISTS "idx_player_computed_mmr_match_id" ON "player_computed_mmr" ("match_id");
CREATE INDEX IF NOT EXISTS "idx_player_computed_mmr_turbo_account_id" ON "player_computed_mmr_turbo" ("account_id");
CREATE INDEX IF NOT EXISTS "idx_player_computed_mmr_turbo_match_id" ON "player_computed_mmr_turbo" ("match_id");
CREATE INDEX IF NOT EXISTS "idx_player_match_history_account_id" ON "player_match_history" ("account_id");
CREATE INDEX IF NOT EXISTS "idx_player_match_history_match_id" ON "player_match_history" ("match_id");
CREATE INDEX IF NOT EXISTS "idx_player_match_history_player_slot" ON "player_match_history" ("player_slot");
CREATE INDEX IF NOT EXISTS "idx_player_matches_match_id" ON "player_matches" ("match_id");
CREATE INDEX IF NOT EXISTS "idx_player_matches_account_id" ON "player_matches" ("account_id");
CREATE INDEX IF NOT EXISTS "idx_player_matches_player_slot" ON "player_matches" ("player_slot");
CREATE INDEX IF NOT EXISTS "idx_player_ratings_account_id" ON "player_ratings" ("account_id");
CREATE INDEX IF NOT EXISTS "idx_player_ratings_match_id" ON "player_ratings" ("match_id");
CREATE INDEX IF NOT EXISTS "idx_players_account_id" ON "players" ("account_id");
CREATE INDEX IF NOT EXISTS "idx_public_matches_match_id" ON "public_matches" ("match_id");
CREATE INDEX IF NOT EXISTS "idx_public_matches_match_seq_num" ON "public_matches" ("match_seq_num");
CREATE INDEX IF NOT EXISTS "idx_rank_tier_account_id" ON "rank_tier" ("account_id");
CREATE INDEX IF NOT EXISTS "idx_rank_tier_2019_1_account_id" ON "rank_tier_2019_1" ("account_id");
CREATE INDEX IF NOT EXISTS "idx_rank_tier_history_account_id" ON "rank_tier_history" ("account_id");
CREATE INDEX IF NOT EXISTS "idx_rating_queue_match_seq_num" ON "rating_queue" ("match_seq_num");
CREATE INDEX IF NOT EXISTS "idx_rating_queue_match_id" ON "rating_queue" ("match_id");
CREATE INDEX IF NOT EXISTS "idx_solo_competitive_rank_account_id" ON "solo_competitive_rank" ("account_id");
CREATE INDEX IF NOT EXISTS "idx_subscriber_account_id" ON "subscriber" ("account_id");
CREATE INDEX IF NOT EXISTS "idx_subscriptions_account_id" ON "subscriptions" ("account_id");
CREATE INDEX IF NOT EXISTS "idx_team_match_team_id" ON "team_match" ("team_id");
CREATE INDEX IF NOT EXISTS "idx_team_match_match_id" ON "team_match" ("match_id");
CREATE INDEX IF NOT EXISTS "idx_team_rating_team_id" ON "team_rating" ("team_id");
CREATE INDEX IF NOT EXISTS "idx_team_rating_match_id" ON "team_rating" ("match_id");
CREATE INDEX IF NOT EXISTS "idx_teams_team_id" ON "teams" ("team_id");
CREATE INDEX IF NOT EXISTS "idx_user_usage_account_id" ON "user_usage" ("account_id");
CREATE INDEX IF NOT EXISTS "idx_webhooks_hook_id" ON "webhooks" ("hook_id");
CREATE INDEX IF NOT EXISTS "idx_webhooks_account_id" ON "webhooks" ("account_id");
// Prediction and snapshot fixtures shaped like GET /api/predictions and GET /api/predictions/{id}
import type { Prediction, PredictionDetail, Snapshot } from '../types'

export const prediction = (fields: Partial<Prediction> = {}): Prediction => ({
  prediction_id: 1,
  created_at: 1_700_000_000,
  team1: { snapshot_id: 7, team_id: 1, name: 'Team A', tag: 'A', logo_url: 'https://example.com/a.png' },
  team2: { snapshot_id: 8, team_id: 2, name: 'Team B', tag: 'B', logo_url: null },
  team1_odds: 1.85,
  team2_odds: 2.05,
  best_of: 3,
  bet_team: 1,
  stake: 100,
  comment: 'Team A looks stronger',
  team1_maps_won: null,
  team2_maps_won: null,
  review_note: null,
  bet_won: null,
  ...fields,
})

export const snapshot = (id: number, team: Snapshot['data']['team'], fields: Partial<Snapshot['data']> = {}): Snapshot => ({
  snapshot_id: id,
  team_id: team.team_id ?? 0,
  team_name: team.team ?? null,
  snapshot_date: '2026-10-22',
  days: 20,
  last_match_time: 0,
  taken_at: 1_700_000_000,
  app_version: '0.25',
  data: { team, summary: null, players: [], ...fields },
})

export const predictionDetail = (fields: Partial<PredictionDetail> = {}): PredictionDetail => ({
  ...prediction(),
  team1_snapshot: snapshot(
    7,
    {
      team: 'Team A',
      tag: 'A',
      team_id: 1,
      rating: 1500,
      roster_source: 'recent_matches',
      roster_games: 10,
      players: [{ name: 'Core One', id: 11, games: 10, is_core: true }],
      other_players: [],
    },
    {
      summary: {
        rating_matches: 40,
        tournament_matches: 10,
        other_matches: 2,
        matches_median: 8,
        matches_avg: 8.5,
        win_percentage: 55,
        rating_win_percentage: 56,
        tournament_win_percentage: 60,
        avg_rank: 120,
        bad_rank_players: 1,
      },
      players: [{ account_id: 11, rank: 45, match_count: 30 }],
    },
  ),
  // An old snapshot: no players lists, no summary
  team2_snapshot: snapshot(8, { team: 'Team B', tag: 'B', team_id: 2 }),
  ...fields,
})

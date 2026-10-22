// Shapes of the backend responses the app reads

// GET /api/statistics: teams[].players[] and teams[].other_players[]
export interface Player {
  name: string
  id: number
  games?: number | null
  is_core?: boolean | null
}

// GET /api/statistics: teams[].league_form
export interface LeagueForm {
  days: number
  matches: number
  wins: number
  losses: number
  win_percentage: number | null
  last_match_time: number | null
}

// Values the backend sends in teams[].roster_state (backend/rosters.py ROSTER_*)
export type RosterState = 'stable' | 'standins' | 'new_team'

// GET /api/statistics: teams[]
export interface TeamData {
  error_code: null | string
  rating: null | number
  delta: number
  logo_url?: string
  task_id?: string | null
  other_players: Player[]
  players: Player[]
  roster_source?: 'recent_matches' | 'pro_players' | null
  roster_games?: number | null
  standins_count?: number
  roster_last_match_time?: number | null
  latest_match_time?: number | null
  latest_match_standins?: number | null
  roster_state?: RosterState | null
  league_form?: LeagueForm | null
  tag: string
  team: string
  team_id: number
}

// GET /api/statistics
export interface Statistics {
  teams: TeamData[]
}

// GET /api/results/{task_id}: summary (backend/stats.py MatchesSummary)
export interface MatchesSummary {
  rating_matches: number
  tournament_matches: number
  other_matches: number
  matches_median: number | null
  matches_avg: number | null
  win_percentage: number | null
  rating_win_percentage: number | null
  tournament_win_percentage: number | null
  avg_rank: number | null
  bad_rank_players: number | null
}

// GET /api/results/{task_id}: results[] (one entry per player: match count and leaderboard rank, or the error that stopped the fetch)
export interface PlayerResult {
  account_id: number
  match_count?: number
  rank?: number | null
  error?: string
}

// GET /api/results/{task_id}. If that request fails, the app keeps the final progress data instead,
// which has only `successful` and `total`, so `summary` is optional here.
// The comparison table reads `summary`; Team Insights reads each player's rank from `results`
export interface StatisticsResult {
  results?: PlayerResult[]
  successful?: number
  total?: number
  summary?: MatchesSummary
}

// GET /api/predictions: [].team1 and [].team2 (name, tag and logo as saved in the snapshot)
export interface PredictionTeam {
  snapshot_id: number
  team_id: number
  name: string | null
  tag: string | null
  logo_url: string | null
}

// GET /api/predictions: one entry; bet_won is null while pending or without a bet
export interface Prediction {
  prediction_id: number
  created_at: number
  team1: PredictionTeam
  team2: PredictionTeam
  team1_odds: number
  team2_odds: number
  best_of: number | null
  bet_team: number | null
  stake: number | null
  comment: string
  team1_maps_won: number | null
  team2_maps_won: number | null
  review_note: string | null
  bet_won: boolean | null
}

// GET /api/snapshots/{id}: data, as the Compare page sent it (old snapshots may lack newer fields)
export interface SnapshotData {
  team: Partial<TeamData>
  summary: MatchesSummary | null
  players: { account_id: number; rank: number | null; match_count: number | null }[]
}

// GET /api/predictions/{id}: team1_snapshot and team2_snapshot
export interface Snapshot {
  snapshot_id: number
  team_id: number
  team_name: string | null
  snapshot_date: string
  days: number
  last_match_time: number
  taken_at: number
  app_version: string
  data: SnapshotData
}

// GET /api/predictions/{id}
export interface PredictionDetail extends Prediction {
  team1_snapshot: Snapshot
  team2_snapshot: Snapshot
}

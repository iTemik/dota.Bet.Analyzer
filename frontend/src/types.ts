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

// GET /api/results/{task_id}. If that request fails, the app keeps the final progress data instead,
// which has only `successful` and `total`, so `summary` is optional here
export interface StatisticsResult {
  results?: unknown[]
  successful?: number
  total?: number
  summary?: MatchesSummary
}

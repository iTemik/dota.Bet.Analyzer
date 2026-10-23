// Helpers shared by the Predictions list and the prediction detail page
import type { Prediction } from './types'

export type Outcome = 'won' | 'lost' | 'no_bet' | 'pending'

export const OUTCOME_LABELS: Record<Outcome, string> = {
  won: 'Won',
  lost: 'Lost',
  no_bet: 'No bet',
  pending: 'Pending',
}

export const isSettled = (p: Prediction): boolean => p.team1_maps_won !== null && p.team2_maps_won !== null

export const outcome = (p: Prediction): Outcome => {
  if (p.bet_team === null) return 'no_bet'
  if (!isSettled(p) || p.bet_won === null) return 'pending'
  return p.bet_won ? 'won' : 'lost'
}

// Series formats accepted by best_of; '' is n/a (unknown, sent as null)
export const SERIES_OPTIONS = [
  { value: '1', label: 'bo1' },
  { value: '2', label: 'bo2' },
  { value: '3', label: 'bo3' },
  { value: '5', label: 'bo5' },
  { value: '', label: 'n/a' },
]

export type BetChoice = '1' | '2' | 'none'

// Decimal input that also accepts a comma ("1,85"); NaN when it is not a number
export const parseDecimal = (value: string): number => (value.trim() ? Number(value.trim().replace(',', '.')) : NaN)

// Field errors of the odds and stake inputs, null where the value is fine
export const decisionErrors = (odds: string[], bet: BetChoice, stake: string) => {
  const oddsErrors = odds.map((value) => {
    if (!value.trim()) return 'Required'
    const number = parseDecimal(value)
    return Number.isFinite(number) && number > 1 ? null : 'Must be a number above 1'
  })
  const stakeError =
    bet === 'none' ? null : !stake.trim() ? 'Required with a bet' : parseDecimal(stake) > 0 ? null : 'Must be above 0'
  return {
    oddsErrors,
    stakeError,
    invalid: oddsErrors.some(Boolean) || Boolean(stakeError),
  }
}

// Body of POST and PUT /api/predictions: odds, series, bet, stake and comment as typed in the form
export const decisionBody = (odds: string[], bestOf: string, bet: BetChoice, stake: string, comment: string) => ({
  team1_odds: parseDecimal(odds[0]),
  team2_odds: parseDecimal(odds[1]),
  best_of: bestOf ? Number(bestOf) : null,
  bet_team: bet === 'none' ? null : Number(bet),
  stake: bet === 'none' ? null : parseDecimal(stake),
  comment,
})

export const seriesLabel = (bestOf: number | null): string => (bestOf ? `bo${bestOf}` : 'n/a')

// Map score "2-1", or "pending" before the review
export const resultText = (p: Prediction): string =>
  isSettled(p) ? `${p.team1_maps_won}-${p.team2_maps_won}` : 'pending'

export const teamLabel = (team: Prediction['team1'], index: number): string => team.name || `Team #${index + 1}`

// Final scores of a series (team 1 maps, team 2 maps), as the backend accepts them; empty when the format is unknown
export const resultOptions = (bestOf: number | null): [number, number][] => {
  if (!bestOf) return []
  if (bestOf === 2) return [[2, 0], [1, 1], [0, 2]]
  const toWin = (bestOf + 1) / 2
  const wins: [number, number][] = Array.from({ length: toWin }, (_, lost) => [toWin, lost])
  return [...wins, ...wins.map(([w, l]): [number, number] => [l, w]).reverse()]
}

// Fetch JSON; throws with the backend's message on an error status. Returns null for 204 No Content
export const requestJson = async <T>(url: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(url, init)
  const data = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) throw new Error(data?.message || `HTTP error! status: ${response.status}`)
  return data as T
}

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

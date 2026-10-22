import { describe, expect, it } from 'vitest'
import { outcome, resultOptions, resultText, seriesLabel } from './predictions'
import type { Prediction } from './types'

const prediction = (fields: Partial<Prediction>): Prediction => ({
  prediction_id: 1,
  created_at: 1_700_000_000,
  team1: { snapshot_id: 1, team_id: 1, name: 'Team A', tag: 'A', logo_url: null },
  team2: { snapshot_id: 2, team_id: 2, name: 'Team B', tag: 'B', logo_url: null },
  team1_odds: 1.8,
  team2_odds: 2.1,
  best_of: 3,
  bet_team: 1,
  stake: 100,
  comment: '',
  team1_maps_won: null,
  team2_maps_won: null,
  review_note: null,
  bet_won: null,
  ...fields,
})

describe('predictions helpers', () => {
  it('lists the final scores valid for each format', () => {
    expect(resultOptions(1)).toEqual([[1, 0], [0, 1]])
    expect(resultOptions(2)).toEqual([[2, 0], [1, 1], [0, 2]])
    expect(resultOptions(3)).toEqual([[2, 0], [2, 1], [1, 2], [0, 2]])
    expect(resultOptions(5)).toEqual([[3, 0], [3, 1], [3, 2], [2, 3], [1, 3], [0, 3]])
    expect(resultOptions(null)).toEqual([])
  })

  it('computes the outcome from the bet and the result', () => {
    expect(outcome(prediction({}))).toBe('pending')
    expect(outcome(prediction({ bet_team: null, stake: null }))).toBe('no_bet')
    expect(outcome(prediction({ team1_maps_won: 2, team2_maps_won: 1, bet_won: true }))).toBe('won')
    expect(outcome(prediction({ team1_maps_won: 0, team2_maps_won: 2, bet_won: false }))).toBe('lost')
  })

  it('formats the series and the result', () => {
    expect(seriesLabel(3)).toBe('bo3')
    expect(seriesLabel(null)).toBe('n/a')
    expect(resultText(prediction({}))).toBe('pending')
    expect(resultText(prediction({ team1_maps_won: 2, team2_maps_won: 1 }))).toBe('2-1')
  })
})

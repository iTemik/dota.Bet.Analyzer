import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ROSTER_STATES, getCorePlayers, getStandins, hasCore, renderName } from './roster'
import type { Player, TeamData } from './types'

const player = (id: number, games: number | null, is_core: boolean | null = null): Player => ({
  name: `Player ${id}`,
  id,
  games,
  is_core,
})

const team = (fields: Partial<TeamData>): TeamData => ({
  error_code: null,
  rating: null,
  delta: 0,
  other_players: [],
  players: [],
  tag: 'T',
  team: 'Team',
  team_id: 1,
  ...fields,
})

const ids = (players: Player[]) => players.map((p) => p.id)

describe('ROSTER_STATES', () => {
  it('ranks the backend roster states from best to worst', () => {
    expect(Object.keys(ROSTER_STATES)).toEqual(['stable', 'standins', 'new_team'])
    expect(ROSTER_STATES.stable.rank).toBeLessThan(ROSTER_STATES.standins.rank)
    expect(ROSTER_STATES.standins.rank).toBeLessThan(ROSTER_STATES.new_team.rank)
  })
})

describe('getCorePlayers', () => {
  it('returns only core players when the roster comes from recent matches', () => {
    const t = team({
      roster_source: 'recent_matches',
      players: [player(1, 10, true), player(2, 10, true), player(3, 4, false)],
    })
    expect(hasCore(t)).toBe(true)
    expect(ids(getCorePlayers(t))).toEqual([1, 2])
  })

  it('returns all main players when there is no clear core', () => {
    const t = team({ roster_source: 'recent_matches', players: [player(1, 5, false), player(2, 5, false)] })
    expect(hasCore(t)).toBe(false)
    expect(ids(getCorePlayers(t))).toEqual([1, 2])
  })

  it('returns all main players when the roster comes from the team list', () => {
    const t = team({ roster_source: 'pro_players', players: [player(1, null, true), player(2, null)] })
    expect(ids(getCorePlayers(t))).toEqual([1, 2])
  })
})

describe('getStandins', () => {
  it('lists non-core players who played, from players and other_players', () => {
    const t = team({
      roster_source: 'recent_matches',
      players: [player(1, 10, true), player(2, 3, false)],
      other_players: [player(3, 1), player(4, 0)],
    })
    expect(ids(getStandins(t))).toEqual([2, 3])
  })

  it('returns no stand-ins when only the core played', () => {
    const t = team({ roster_source: 'recent_matches', players: [player(1, 10, true)], other_players: [player(2, 0)] })
    expect(getStandins(t)).toEqual([])
  })
})

describe('renderName', () => {
  it('returns a named player as is', () => {
    expect(renderName(player(1, 1))).toBe('Player 1')
  })

  it('shows an unnamed account as an ID', () => {
    render(<>{renderName({ name: '#12345', id: 12345 })}</>)
    const id = screen.getByText('ID 12345')
    expect(id).toHaveClass('account-id')
    expect(id).toHaveAttribute('title', 'No player name on OpenDota; this is the account ID')
  })
})

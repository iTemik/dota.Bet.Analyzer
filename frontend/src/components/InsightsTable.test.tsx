import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Player, TeamData } from '../types'
import InsightsTable from './InsightsTable'

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

// Cells of the row whose label matches, without the label cell
const rowCells = (label: string) => {
  const row = screen.getByText(label).closest('tr') as HTMLElement
  return within(row).getAllByRole('cell').slice(1)
}

describe('InsightsTable', () => {
  it('renders core players with games and ranks from props', () => {
    const first = team({
      team: 'Alpha',
      roster_source: 'recent_matches',
      roster_games: 10,
      players: [player(1, 10, true), player(2, 8, true)],
    })
    render(<InsightsTable teams={[first, team({ team: 'Beta' })]} ranks={[new Map([[1, 120], [2, null]]), new Map()]} />)

    expect(screen.getByText('Alpha')).toBeInTheDocument()
    expect(screen.getByText('Beta')).toBeInTheDocument()
    const [core] = rowCells('Core Players')
    expect(core).toHaveTextContent('Player 1 · games: 10 · rank: 120')
    expect(core).toHaveTextContent('Player 2 · games: 8 of 10 · rank: -')
  })

  it('lists stand-ins and other players separately', () => {
    const first = team({
      roster_source: 'recent_matches',
      players: [player(1, 10, true), player(3, 2, false)],
      other_players: [player(4, 0)],
    })
    render(<InsightsTable teams={[first, team({})]} ranks={[new Map(), new Map()]} />)

    expect(rowCells('Stand-ins')[0]).toHaveTextContent('Player 3 · games: 2')
    expect(rowCells('Other Players')[0]).toHaveTextContent('Player 4')
    expect(rowCells('Other Players')[0]).not.toHaveTextContent('Player 3')
  })

  it('works without ranks and shows "-" for fields an old snapshot lacks', () => {
    // A snapshot saved before some fields existed: no roster source, no match times
    const old = { team: 'Old', players: [player(1, 5)] } as unknown as TeamData
    render(<InsightsTable teams={[old, undefined]} ranks={[]} />)

    expect(screen.getByText('Team #2')).toBeInTheDocument()
    expect(rowCells('Core Players')[0]).toHaveTextContent('Player 1 · games: 5')
    expect(rowCells('Core Players')[0]).toHaveTextContent('unconfirmed: no recent tournament match')
    expect(rowCells('Stand-ins').map((c) => c.textContent)).toEqual(['-', '-'])
    expect(rowCells('Other Players').map((c) => c.textContent)).toEqual(['None', '-'])
    expect(rowCells('Last Tournament Match').map((c) => c.textContent)).toEqual(['-', '-'])
    expect(rowCells('Median Match Duration').map((c) => c.textContent)).toEqual(['-', '-'])
  })

  it('shows the median match duration as minutes and seconds', () => {
    const form = (duration_median: number) => ({ days: 20, matches: 3, wins: 2, losses: 1, win_percentage: 66.7, last_match_time: null, duration_median })
    render(<InsightsTable teams={[team({ league_form: form(2052.5) }), team({ league_form: form(1805) })]} ranks={[]} />)
    expect(rowCells('Median Match Duration').map((c) => c.textContent)).toEqual(['34:13', '30:05'])
  })

  it('shows the team tag and ID first, without an info icon', () => {
    render(<InsightsTable teams={[team({ tag: 'ALP', team_id: 39 }), undefined]} ranks={[]} />)
    expect(rowCells('Team Tag').map((c) => c.textContent)).toEqual(['ALP', '-'])
    expect(rowCells('Team ID').map((c) => c.textContent)).toEqual(['39', '-'])
    expect(screen.getAllByRole('row')[1]).toHaveTextContent(/^Team Tag/)
    expect(within(screen.getByText('Team Tag')).queryByRole('button', { name: 'Row info' })).not.toBeInTheDocument()
  })

  it('shows an info tooltip on each insight row', () => {
    render(<InsightsTable teams={[team({}), team({})]} ranks={[]} />)
    for (const label of ['Core Players', 'Stand-ins', 'Other Players', 'Last Tournament Match', 'Median Match Duration']) {
      expect(within(screen.getByText(label)).getByRole('tooltip')).toHaveTextContent(/^Description: /)
    }
    expect(within(screen.getByText('Stand-ins')).getByRole('tooltip')).toHaveTextContent('outside the core who played')
  })
})

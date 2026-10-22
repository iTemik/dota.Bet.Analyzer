import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { MatchesSummary, TeamData } from '../types'
import ComparisonTable from './ComparisonTable'

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

const summary = (fields: Partial<MatchesSummary>): MatchesSummary => ({
  rating_matches: 0,
  tournament_matches: 0,
  other_matches: 0,
  matches_median: null,
  matches_avg: null,
  win_percentage: null,
  rating_win_percentage: null,
  tournament_win_percentage: null,
  avg_rank: null,
  bad_rank_players: null,
  ...fields,
})

// Cells of the row whose label matches, without the label cell
const rowCells = (label: RegExp) => {
  const row = screen.getByText(label).closest('tr') as HTMLElement
  return within(row).getAllByRole('cell').slice(1)
}

describe('ComparisonTable', () => {
  it('renders team names, logos and stats from props', () => {
    const teams = [
      team({ team: 'Alpha', tag: 'ALP', rating: 1500, logo_url: 'a.png' }),
      team({ team: 'Beta', tag: 'BET', rating: 1300 }),
    ]
    render(<ComparisonTable teams={teams} summaries={[null, null]} showSummaryRows={false} days={20} />)

    expect(screen.getByText('Alpha')).toBeInTheDocument()
    expect(screen.getByText('Beta')).toBeInTheDocument()
    expect(screen.getByAltText('Team 1 Logo')).toHaveAttribute('src', 'a.png')
    expect(screen.queryByAltText('Team 2 Logo')).not.toBeInTheDocument()
    expect(rowCells(/^Team Tag$/).map((c) => c.textContent)).toEqual(['ALP', 'BET'])
  })

  it('colours the better rating green and the worse red', () => {
    const teams = [team({ rating: 1500 }), team({ rating: 1300 })]
    render(<ComparisonTable teams={teams} summaries={[null, null]} showSummaryRows={false} days={20} />)

    const [first, second] = rowCells(/^Rating$/)
    expect(first).toHaveStyle({ backgroundColor: '#6b9d7a' })
    expect(second).toHaveStyle({ backgroundColor: '#9d6b6b' })
  })

  it('hides summary rows until asked to show them', () => {
    const teams = [team({}), team({})]
    const { rerender } = render(<ComparisonTable teams={teams} summaries={[null, null]} showSummaryRows={false} days={20} />)
    expect(screen.queryByText('Rating Matches')).not.toBeInTheDocument()

    const summaries = [summary({ rating_matches: 40, avg_rank: 500 }), summary({ rating_matches: 10, avg_rank: 900 })]
    rerender(<ComparisonTable teams={teams} summaries={summaries} showSummaryRows days={20} />)
    expect(rowCells(/^Rating Matches$/).map((c) => c.textContent)).toEqual(['40', '10'])
    // Lower average rank is better
    expect(rowCells(/^Average Player Rank$/)[0]).toHaveStyle({ backgroundColor: '#6b9d7a' })
  })

  it('uses the days prop in the record label when the team has no league form', () => {
    render(<ComparisonTable teams={[team({}), team({})]} summaries={[null, null]} showSummaryRows={false} days={30} />)
    expect(screen.getByText('Tournaments Record (30d)')).toBeInTheDocument()
  })

  it('shows "-" for fields an old snapshot lacks', () => {
    // A snapshot saved before some fields existed: only the basic team fields are there
    const old = { team: 'Old', players: [] } as unknown as TeamData
    render(<ComparisonTable teams={[old, undefined]} summaries={[{} as MatchesSummary, null]} showSummaryRows days={20} />)

    expect(screen.getByText('Team #2')).toBeInTheDocument()
    expect(rowCells(/^Roster Changes$/).map((c) => c.textContent)).toEqual(['-', '-'])
    expect(rowCells(/^Pub Win %$/).map((c) => c.textContent)).toEqual(['-', '-'])
    expect(rowCells(/^Last Match$/).map((c) => c.textContent)).toEqual(['-', '-'])
  })
})

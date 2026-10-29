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

  it('uses the days prop in the record label when the first team has no league form', () => {
    const form = { days: 20, matches: 4, wins: 3, losses: 1, win_percentage: 75, last_match_time: null }
    render(<ComparisonTable teams={[team({}), team({ league_form: form })]} summaries={[null, null]} showSummaryRows={false} days={30} />)
    expect(rowCells(/^Tournament matches, last 30 days$/).map((c) => c.textContent)).toEqual(['-', '3-1 (75.0%)'])
  })

  it('adds a plus sign to a positive last match rating', () => {
    render(<ComparisonTable teams={[team({ delta: 12.34 }), team({ delta: -5 })]} summaries={[null, null]} showSummaryRows={false} days={20} />)
    expect(rowCells(/^Last match rating$/).map((c) => c.textContent)).toEqual(['+12.3', '-5.0'])
  })

  it('shows the rating change over the window, coloured only beyond 16 points', () => {
    const { rerender } = render(
      <ComparisonTable teams={[team({ rating_change: 40.26 }), team({ rating_change: -3 })]} summaries={[null, null]} showSummaryRows={false} days={20} />,
    )
    let cells = rowCells(/^Rating change, last 20 days$/)
    expect(cells.map((c) => c.textContent)).toEqual(['+40.3', '-3.0'])
    expect(cells[0]).toHaveStyle({ backgroundColor: '#6b9d7a' })
    expect(cells[1]).toHaveStyle({ backgroundColor: '#9d6b6b' })

    rerender(<ComparisonTable teams={[team({ rating_change: 10 }), team({ rating_change: -5 })]} summaries={[null, null]} showSummaryRows={false} days={20} />)
    cells = rowCells(/^Rating change, last 20 days$/)
    expect(cells.map((c) => c.style.backgroundColor)).toEqual(['transparent', 'transparent'])
  })

  it('shows the Radiant record and top 1 and top 2 GPM and XPM medians from the league form', () => {
    const form = (radiant_wins: number, gpm_top1: number) => ({
      days: 20,
      matches: 6,
      wins: 4,
      losses: 2,
      win_percentage: 66.7,
      last_match_time: null,
      radiant_matches: 4,
      radiant_wins,
      radiant_win_percentage: (100 * radiant_wins) / 4,
      farm: { games: 6, gold_per_min_top1: gpm_top1, gold_per_min_top2: 600.5, xp_per_min_top1: 800, xp_per_min_top2: 700 },
    })
    const teams = [team({ league_form: form(3, 750) }), team({ league_form: { ...form(1, 650), farm: null } })]
    render(<ComparisonTable teams={teams} summaries={[null, null]} showSummaryRows={false} days={20} />)

    const radiant = rowCells(/^Radiant Win %$/)
    expect(radiant.map((c) => c.textContent)).toEqual(['3-1 (75.0%)', '1-3 (25.0%)'])
    expect(radiant[0]).toHaveStyle({ backgroundColor: '#6b9d7a' })
    // A team without parsed games has "-" and no colours
    const top1 = rowCells(/^Top 1 GPM \(median\)$/)
    expect(top1.map((c) => c.textContent)).toEqual(['750', '-'])
    expect(top1[0].style.backgroundColor).toBe('transparent')
    expect(rowCells(/^Top 2 GPM \(median\)$/).map((c) => c.textContent)).toEqual(['601', '-'])
    expect(rowCells(/^Top 2 XPM \(median\)$/).map((c) => c.textContent)).toEqual(['700', '-'])
    expect(within(screen.getByText(/^Top 1 XPM \(median\)$/)).getByRole('tooltip')).toHaveTextContent('ranked separately')
  })

  it('hides rows that are empty for both teams and keeps rows with a value on one side', () => {
    // A snapshot saved before some fields existed: only the basic team fields are there
    const old = { team: 'Old', tag: 'OLD', players: [] } as unknown as TeamData
    const summaries = [{ rating_matches: 5 } as MatchesSummary, null]
    render(<ComparisonTable teams={[old, undefined]} summaries={summaries} showSummaryRows days={20} />)

    expect(screen.getByText('Team #2')).toBeInTheDocument()
    expect(rowCells(/^Team Tag$/).map((c) => c.textContent)).toEqual(['OLD', '-'])
    expect(rowCells(/^Rating Matches$/).map((c) => c.textContent)).toEqual(['5', '-'])
    for (const label of ['Roster Changes', 'Pub Win %', 'Last Match', 'Last match rating', 'Radiant Win %', 'Top 1 GPM (median)']) {
      expect(screen.queryByText(label)).not.toBeInTheDocument()
    }
  })

  it('shows an info icon with description, colour rules and assumption on the stat rows', () => {
    const summaries = [summary({ bad_rank_players: 1 }), summary({ bad_rank_players: 2 })]
    render(<ComparisonTable teams={[team({ rating: 1500 }), team({ rating: 1300 })]} summaries={summaries} showSummaryRows days={20} />)

    // Plain team fields have no info icon
    expect(within(screen.getByText(/^Team Tag$/)).queryByRole('button', { name: 'Row info' })).not.toBeInTheDocument()
    const label = screen.getByText(/^Rating$/)
    const tooltip = within(label).getByRole('tooltip')
    expect(within(label).getByRole('button', { name: 'Row info' })).toHaveAttribute('tabindex', '0')
    expect(tooltip).toHaveTextContent('Description: OpenDota Elo rating')
    expect(tooltip).toHaveTextContent('Color Highlighting: Higher is green')
    expect(tooltip).toHaveTextContent('Assumption:')
    // The Russian note moved from the label into the tooltip
    const lowRank = screen.getByText(/^Low Rank Players$/)
    expect(lowRank).toHaveTextContent(/^Low Rank Playersi/)
    expect(within(lowRank).getByRole('tooltip')).toHaveTextContent('тысячники')
  })

  it('colours a long-ago or missing last match red when the other team played in the last 14 days', () => {
    const now = 100 * 86400
    const at = (daysAgo: number) => team({ roster_last_match_time: now - daysAgo * 86400 })
    const { rerender } = render(<ComparisonTable teams={[at(3), at(20)]} summaries={[null, null]} showSummaryRows={false} days={20} now={now} />)
    let [first, second] = rowCells(/^Last Match$/)
    expect(first.style.backgroundColor).toBe('transparent')
    expect(second).toHaveStyle({ backgroundColor: '#9d6b6b' })

    // No date counts as a long break
    rerender(<ComparisonTable teams={[team({}), at(3)]} summaries={[null, null]} showSummaryRows={false} days={20} now={now} />)
    ;[first, second] = rowCells(/^Last Match$/)
    expect(first).toHaveStyle({ backgroundColor: '#9d6b6b' })
    expect(second.style.backgroundColor).toBe('transparent')

    // Both on a break or both recent: no colour
    rerender(<ComparisonTable teams={[at(15), at(30)]} summaries={[null, null]} showSummaryRows={false} days={20} now={now} />)
    expect(rowCells(/^Last Match$/).map((c) => c.style.backgroundColor)).toEqual(['transparent', 'transparent'])
    rerender(<ComparisonTable teams={[at(1), at(13)]} summaries={[null, null]} showSummaryRows={false} days={20} now={now} />)
    expect(rowCells(/^Last Match$/).map((c) => c.style.backgroundColor)).toEqual(['transparent', 'transparent'])
  })
})

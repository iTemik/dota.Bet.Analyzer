import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Player, TeamData, TeamMeta } from '../types'
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
    expect(rowCells('Last Tournament Match with core players').map((c) => c.textContent)).toEqual(['-', '-'])
    expect(rowCells('Median Match Duration').map((c) => c.textContent)).toEqual(['-', '-'])
    expect(rowCells('Radiant Win %').map((c) => c.textContent)).toEqual(['-', '-'])
  })

  it('shows the Radiant record without colours', () => {
    const form = (radiant_wins: number) => ({
      days: 20,
      matches: 6,
      wins: 4,
      losses: 2,
      win_percentage: 66.7,
      last_match_time: null,
      radiant_matches: 4,
      radiant_wins,
      radiant_win_percentage: (100 * radiant_wins) / 4,
    })
    render(<InsightsTable teams={[team({ league_form: form(3) }), team({ league_form: form(1) })]} ranks={[]} />)
    const cells = rowCells('Radiant Win %')
    expect(cells.map((c) => c.textContent)).toEqual(['3-1 (75.0%)', '1-3 (25.0%)'])
    expect(cells[0].style.backgroundColor).toBe('')
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
    for (const label of ['Core Players', 'Stand-ins', 'Other Players', 'Last Tournament Match with core players', 'Median Match Duration']) {
      expect(within(screen.getByText(label)).getByRole('tooltip')).toHaveTextContent(/^Description: /)
    }
    expect(within(screen.getByText('Stand-ins')).getByRole('tooltip')).toHaveTextContent('outside the core who played')
  })

  describe('team meta', () => {
    const DAY = 24 * 60 * 60
    const deepStart = 1_790_000_000
    const recentStart = deepStart + 40 * DAY
    const meta = (fields: Partial<TeamMeta> = {}): TeamMeta => ({
      state: 'actively',
      patch: '7.39',
      recent: { start: recentStart, games: 19, meta_games: 14, meta_games_pct: 73.7, meta_picks_pct: 58.2 },
      deep: { start: deepStart, games: 30, meta_games: 20, meta_games_pct: 66.7, meta_picks_pct: 57.6 },
      pro_meta_picks_pct: 45.1,
      heroes: [
        { hero_id: 1, localized_name: 'Anti-Mage', icon: 'am.png', ultra: true, games: 6, recent_games: 4, practice_players: 1 },
        { hero_id: 2, localized_name: 'Axe', icon: 'axe.png', ultra: false, games: 2, recent_games: 0, practice_players: 0 },
        { hero_id: 3, localized_name: 'Bane', icon: 'bane.png', ultra: false, games: 0, recent_games: 0, practice_players: 2 },
      ],
      players: [],
      params: { meta_min_heroes: 3, deep_days: 60 },
      ...fields,
    })
    const since = (start: number) => `Since ${new Date(start * 1000).toLocaleDateString()}`

    it('shows the state, the meta picks share and both windows', () => {
      render(<InsightsTable teams={[team({}), team({})]} ranks={[new Map(), new Map()]} metas={[meta(), undefined]} />)

      const [first, second] = rowCells('Meta')
      expect(first).toHaveTextContent('Actively plays meta')
      expect(first).toHaveTextContent('58% meta picks (pro avg 45%)')
      expect(first).toHaveTextContent(`${since(recentStart)}: 3+ meta heroes in 14 of 19 games (74%)`)
      expect(first).toHaveTextContent(`${since(deepStart)}: 3+ meta heroes in 20 of 30 games (67%)`)
      expect(first).toHaveTextContent('patch 7.39')
      expect(second).toHaveTextContent('-')
    })

    it.each([
      ['tries', 'Tries to play meta'],
      ['players_know', 'Players know meta'],
      ['doesnt_play', "Doesn't play meta"],
      ['no_info', 'No info'],
    ] as const)('labels the %s state', (state, label) => {
      render(<InsightsTable teams={[team({}), team({})]} ranks={[new Map(), new Map()]} metas={[meta({ state }), null]} />)

      expect(rowCells('Meta')[0]).toHaveTextContent(label)
    })

    it('shows one window when the patch cut both to the same start, and no share without games', () => {
      const window = { start: recentStart, games: 0, meta_games: 0, meta_games_pct: null, meta_picks_pct: null }
      render(
        <InsightsTable
          teams={[team({}), team({})]}
          ranks={[new Map(), new Map()]}
          metas={[meta({ state: 'no_info', recent: window, deep: window, heroes: [] }), null]}
        />,
      )

      const [cell] = rowCells('Meta')
      expect(cell).toHaveTextContent(`No info${since(recentStart)}: 3+ meta heroes in 0 of 0 gamespatch 7.39`)
      expect(rowCells('Meta Heroes')[0]).toHaveTextContent('None')
    })

    it('shows an unavailable meta with its error', () => {
      render(
        <InsightsTable teams={[team({}), team({})]} ranks={[new Map(), new Map()]} metas={[{ error: 'heroStats down' }, null]} />,
      )

      expect(rowCells('Meta')[0]).toHaveTextContent('Unavailable: heroStats down')
      expect(rowCells('Meta Heroes')[0]).toHaveTextContent('-')
    })

    it('lists meta heroes with icon, games and tags', () => {
      render(<InsightsTable teams={[team({}), team({})]} ranks={[new Map(), new Map()]} metas={[meta(), null]} />)

      const [cell] = rowCells('Meta Heroes')
      const heroes = within(cell).getAllByText(/Anti-Mage|Axe|Bane/).map((el) => el.closest('.team-meta-hero'))
      expect(heroes[0]).toHaveTextContent('Anti-Mage · 6 games · practised by 1ultra')
      expect(heroes[1]).toHaveTextContent('Axe · 2 games60d')
      expect(heroes[2]).toHaveTextContent('Bane · practised by 2pub')
      expect(within(cell).getByAltText('Anti-Mage icon')).toHaveAttribute('src', 'am.png')
      expect(within(cell).getByText('ultra')).toHaveClass('meta-tag-ultra')
      expect(within(cell).getByText('60d')).toHaveAttribute('title', 'Picked only in the last 60 days, not in the recent window')
      expect(within(cell).queryByText('recent')).not.toBeInTheDocument()
    })

    it('hides the meta rows without team meta (saved snapshots)', () => {
      render(<InsightsTable teams={[team({}), team({})]} ranks={[new Map(), new Map()]} />)

      expect(screen.queryByText('Meta')).not.toBeInTheDocument()
      expect(screen.queryByText('Meta Heroes')).not.toBeInTheDocument()
    })
  })
})

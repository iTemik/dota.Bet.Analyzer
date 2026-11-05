import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { formatDate } from '../format'
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
    const now = Math.floor(Date.now() / 1000)
    const deepStart = now - 60 * DAY
    const recentStart = now - 20 * DAY
    const meta = (fields: Partial<TeamMeta> = {}): TeamMeta => ({
      state: 'actively',
      patch: '7.39',
      pool_state: 'normal',
      sample: { start: recentStart, window: 'recent', games: 15, meta2_games_pct: 80, meta3_games_pct: 40, meta_picks_pct: 58.2, heroes: 32 },
      recent: { start: recentStart, games: 28, meta_picks_pct: 58.2, heroes: 40 },
      deep: { start: deepStart, games: 45, meta_picks_pct: 52.4, heroes: 56 },
      pro_meta_picks_pct: 49.8,
      meta_heroes_total: 14,
      heroes: [
        { hero_id: 2, localized_name: 'Axe', icon: 'axe.png', ultra: false, games: 3, recent_games: 0, practice_players: 0 },
        { hero_id: 1, localized_name: 'Anti-Mage', icon: 'am.png', ultra: true, games: 6, recent_games: 4, practice_players: 1 },
        { hero_id: 3, localized_name: 'Bane', icon: 'bane.png', ultra: false, games: 4, recent_games: 1, practice_players: 2 },
      ],
      players: [],
      params: { deep_days: 60 },
      ...fields,
    })

    it('shows the state with the sample’s 2+ and 3+ shares, coloured by the thresholds', () => {
      render(<InsightsTable teams={[team({}), team({})]} ranks={[new Map(), new Map()]} metas={[meta(), undefined]} />)

      const [first, second] = rowCells('Meta')
      expect(first).toHaveTextContent(/^Actively plays meta · 2\+ 80% · 3\+ 40%$/)
      // 80% is above the actively threshold (65%): green; 40% is between 35% and 50%: plain
      expect(within(first).getByText('80%')).toHaveClass('team-meta-pos')
      expect(within(first).getByText('40%')).not.toHaveClass('team-meta-pos', 'team-meta-neg')
      expect(first.querySelector('.team-meta')).toHaveAttribute(
        'title',
        "Actively: 2+ meta heroes in over 65% of games and 3+ in over 50%. Doesn't play: 2+ in 50% or less, or 3+ in 35% or less. Tries: in between.\n" +
          `From the 15 newest tournament games since ${formatDate(recentStart)} (all in the recent window); fewer than 10 games: decided by the players' practice.\n` +
          'Meta heroes are 58% of these picks (all pro games: 50%).',
      )
      expect(second).toHaveTextContent('-')
    })

    it('colours a share at or below the doesn’t play threshold red', () => {
      const sample = { start: deepStart, window: 'deep' as const, games: 15, meta2_games_pct: 60, meta3_games_pct: 27, meta_picks_pct: 30, heroes: 46 }
      render(<InsightsTable teams={[team({}), team({})]} ranks={[new Map(), new Map()]} metas={[meta({ state: 'doesnt_play', sample }), null]} />)

      const [cell] = rowCells('Meta')
      expect(cell).toHaveTextContent(/^Doesn't play meta · 2\+ 60% · 3\+ 27%$/)
      expect(within(cell).getByText('27%')).toHaveClass('team-meta-neg')
      expect(cell.querySelector('.team-meta')?.getAttribute('title')).toContain('(reaching into the 60-day window)')
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

    it('shows only the state with too few games', () => {
      const sample = { start: null, window: 'deep' as const, games: 4, meta2_games_pct: 50, meta3_games_pct: 25, meta_picks_pct: 30, heroes: 15 }
      render(
        <InsightsTable
          teams={[team({}), team({})]}
          ranks={[new Map(), new Map()]}
          metas={[meta({ state: 'no_info', pool_state: null, sample, heroes: [] }), null]}
        />,
      )

      expect(rowCells('Meta')[0]).toHaveTextContent(/^No info$/)
      expect(rowCells('Meta Heroes')[0]).toHaveTextContent(/^0 of 14 meta heroes$/)
    })

    it('lists every meta state in bold in the Meta tooltip', () => {
      render(<InsightsTable teams={[team({}), team({})]} ranks={[new Map(), new Map()]} metas={[meta(), null]} />)

      const label = screen.getByText('Meta', { selector: '.row-label' })
      const states = [...within(label).getByRole('tooltip').querySelectorAll('li b')].map((b) => b.textContent)
      expect(states).toEqual(['Actively plays meta', 'Tries to play meta', 'Doesn’t play meta', 'Players know meta', 'No info'])
    })

    it('shows an unavailable meta with its error', () => {
      render(
        <InsightsTable teams={[team({}), team({})]} ranks={[new Map(), new Map()]} metas={[{ error: 'heroStats down' }, null]} />,
      )

      expect(rowCells('Meta')[0]).toHaveTextContent('Unavailable: heroStats down')
      expect(rowCells('Meta Heroes')[0]).toHaveTextContent('-')
    })

    it('lists meta heroes by name with icon, games and tags, details in the tooltip', () => {
      render(<InsightsTable teams={[team({}), team({})]} ranks={[new Map(), new Map()]} metas={[meta(), null]} />)

      const [cell] = rowCells('Meta Heroes')
      const heroes = [...cell.querySelectorAll('.team-meta-hero')]
      // Each hero: name, games, an (i) tooltip and its tags
      expect(heroes.map((h) => h.textContent?.replace(/iDescription: [^]*?\)\./, ' (i) '))).toEqual([
        'Anti-Mage · 6 (i) ultra',
        'Axe · 3 (i) 60d',
        'Bane · 4 (i) ',
      ])
      expect(cell.querySelector('.team-meta-count')).toHaveTextContent(/^3 of 14 meta heroes$/)
      expect(within(heroes[0] as HTMLElement).getByRole('tooltip')).toHaveTextContent(
        'Description: 6 games in 60 days, 4 in the recent window. Practised by 1 core player (3+ league games, or 5+ league and pub games, in 60 days).',
      )
      expect(within(heroes[2] as HTMLElement).getByRole('tooltip')).toHaveTextContent('Practised by 2 core players')
      expect(within(cell).getByAltText('Anti-Mage icon')).toHaveAttribute('src', 'am.png')
      expect(within(cell).getByText('ultra')).toHaveClass('meta-tag-ultra')
      expect(within(cell).getByText('60d')).toHaveAttribute('title', 'Picked only in the last 60 days, not in the recent window')
      expect(cell.textContent?.replace(/Description: [^]*?days\)\./g, '')).not.toMatch(/ractised/)
    })

    it('hides the meta rows without team meta (saved snapshots)', () => {
      render(<InsightsTable teams={[team({}), team({})]} ranks={[new Map(), new Map()]} />)

      expect(screen.queryByText('Meta')).not.toBeInTheDocument()
      expect(screen.queryByText('Meta Heroes')).not.toBeInTheDocument()
    })
  })
})

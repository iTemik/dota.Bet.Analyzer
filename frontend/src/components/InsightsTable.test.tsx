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
      recent: { start: recentStart, games: 28, meta_games: 16, meta_games_pct: 57.1, meta_picks_pct: 58.2 },
      deep: { start: deepStart, games: 45, meta_games: 24, meta_games_pct: 53.3, meta_picks_pct: 52.4 },
      pro_meta_picks_pct: 49.8,
      meta_heroes_total: 14,
      heroes: [
        { hero_id: 2, localized_name: 'Axe', icon: 'axe.png', ultra: false, games: 3, recent_games: 0, practice_players: 0 },
        { hero_id: 1, localized_name: 'Anti-Mage', icon: 'am.png', ultra: true, games: 6, recent_games: 4, practice_players: 1 },
        { hero_id: 3, localized_name: 'Bane', icon: 'bane.png', ultra: false, games: 4, recent_games: 1, practice_players: 2 },
      ],
      players: [],
      params: { meta_min_heroes: 3, deep_days: 60 },
      ...fields,
    })
    const since = (start: number) => `Since ${new Date(start * 1000).toLocaleDateString()}`

    it('shows the state with one coloured share of meta games, details in the tooltip', () => {
      render(<InsightsTable teams={[team({}), team({})]} ranks={[new Map(), new Map()]} metas={[meta(), undefined]} />)

      const [first, second] = rowCells('Meta')
      // Actively plays meta comes from the recent window: 57% of its games, under 65% so red
      expect(first).toHaveTextContent(/^Actively plays meta · 57%$/)
      expect(within(first).getByText('57%')).toHaveClass('team-meta-neg')
      expect(first.querySelector('.team-meta')).toHaveAttribute(
        'title',
        'Share of the team\'s games with 3+ meta heroes in the draft (plays meta: 65%+ of at least 20 games).\n' +
          `${since(recentStart)}: 3+ meta heroes in 16 of 28 games (57%)\n` +
          `${since(deepStart)}: 3+ meta heroes in 24 of 45 games (53%)\n` +
          'Meta heroes are 52% of all the team\'s picks (all pro games: 50%).',
      )
      expect(second).toHaveTextContent('-')
    })

    it('takes the share from the deeper window for other states and colours it green at the threshold', () => {
      const deep = { start: deepStart, games: 45, meta_games: 30, meta_games_pct: 66.7, meta_picks_pct: 60 }
      render(<InsightsTable teams={[team({}), team({})]} ranks={[new Map(), new Map()]} metas={[meta({ state: 'tries', deep }), null]} />)

      const [cell] = rowCells('Meta')
      expect(cell).toHaveTextContent(/^Tries to play meta · 67%$/)
      expect(within(cell).getByText('67%')).toHaveClass('team-meta-pos')
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

    it('shows only the state without games, and one window when the patch cut both to the same start', () => {
      const window = { start: now - 7 * DAY, games: 0, meta_games: 0, meta_games_pct: null, meta_picks_pct: null }
      render(
        <InsightsTable
          teams={[team({}), team({})]}
          ranks={[new Map(), new Map()]}
          metas={[meta({ state: 'no_info', recent: window, deep: window, heroes: [] }), null]}
        />,
      )

      const [cell] = rowCells('Meta')
      expect(cell).toHaveTextContent(/^No info$/)
      expect(cell.querySelector('.team-meta')?.getAttribute('title')?.split('\n')).toHaveLength(3)
      expect(rowCells('Meta Heroes')[0]).toHaveTextContent(/^0 of 14 meta heroes$/)
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

    it('shows the shares of drafts with 2+ and 3+ meta heroes per window', () => {
      const recent = { start: recentStart, games: 28, meta_games: 16, meta_games_pct: 57.1, meta2_games_pct: 75, meta3_games_pct: 50.4, meta_picks_pct: 58.2 }
      const deep = { start: deepStart, games: 45, meta_games: 24, meta_games_pct: 53.3, meta2_games_pct: 60, meta3_games_pct: 33.3, meta_picks_pct: 52.4 }
      render(<InsightsTable teams={[team({}), team({})]} ranks={[new Map(), new Map()]} metas={[meta({ recent, deep }), undefined]} />)

      const [first, second] = rowCells('Meta Drafts')
      expect(within(first).getByText('20d: 2+ 75% · 3+ 50%')).toHaveAttribute('title', `28 tournament games since ${formatDate(recentStart)}`)
      expect(within(first).getByText('60d: 2+ 60% · 3+ 33%')).toBeInTheDocument()
      expect(second).toHaveTextContent('-')
    })

    it('shows the hero pool: different heroes and games per window', () => {
      const recent = { start: recentStart, games: 25, meta_games: 10, meta_games_pct: 40, meta_picks_pct: 30, heroes: 34 }
      const deep = { start: deepStart, games: 45, meta_games: 20, meta_games_pct: 44, meta_picks_pct: 31, heroes: 56 }
      render(<InsightsTable teams={[team({}), team({})]} ranks={[new Map(), new Map()]} metas={[meta({ recent, deep }), undefined]} />)

      const [first, second] = rowCells('Hero Pool')
      expect(within(first).getByText('20d: 34 heroes in 25 games (1.4 per game)')).toBeInTheDocument()
      expect(within(first).getByText('60d: 56 heroes in 45 games (1.2 per game)')).toBeInTheDocument()
      expect(second).toHaveTextContent('-')
    })

    it('shows the core players’ meta hero games in pubs and in all games', () => {
      const games = (meta_games: number, total: number, players = 5) => ({ games: total, meta_games, meta_games_pct: Math.round((1000 * meta_games) / total) / 10, players })
      const player_games = { recent: games(50, 100), deep: games(120, 250), pub_deep: games(90, 210, 4) }
      render(<InsightsTable teams={[team({}), team({})]} ranks={[new Map(), new Map()]} metas={[meta({ player_games }), meta()]} />)

      const [first, second] = rowCells('Meta Players')
      expect(within(first).getByText('Pubs 60d: 43%')).toHaveAttribute('title', '90 of 210 games on a meta hero (4 of 5 core players with data)')
      expect(within(first).getByText('All 20d: 50%')).toBeInTheDocument()
      expect(within(first).getByText('All 60d: 48%')).toBeInTheDocument()
      expect(second).toHaveTextContent('-')
    })

    it('hides the meta rows without team meta (saved snapshots)', () => {
      render(<InsightsTable teams={[team({}), team({})]} ranks={[new Map(), new Map()]} />)

      expect(screen.queryByText('Meta')).not.toBeInTheDocument()
      expect(screen.queryByText('Meta Heroes')).not.toBeInTheDocument()
      expect(screen.queryByText('Meta Drafts')).not.toBeInTheDocument()
      expect(screen.queryByText('Meta Players')).not.toBeInTheDocument()
      expect(screen.queryByText('Hero Pool')).not.toBeInTheDocument()
    })
  })
})

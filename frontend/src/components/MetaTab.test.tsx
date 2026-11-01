import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Meta, MetaHero } from '../types'
import { DEFAULT_META_PARAMS, META_PARAMS_KEY } from '../meta'
import { formatShortCount } from '../format'
import MetaTab from './MetaTab'

const hero = (hero_id: number, name: string, fields: Partial<MetaHero>): MetaHero => ({
  hero_id,
  localized_name: name,
  icon: `https://cdn/${name}.png`,
  meta: ['pro'],
  pro_picks: 0,
  pro_bans: 0,
  pro_wins: 0,
  pro_pick_ban_rate: null,
  pro_win_rate: null,
  pub_picks: 0,
  pub_wins: 0,
  pub_pick_rate: null,
  pub_win_rate: null,
  ...fields,
})

// Backend order: ultra, pro, then pub only
const meta: Meta = {
  fetched_at: 1_800_000_000,
  params: DEFAULT_META_PARAMS,
  pro_matches: 76,
  pub_matches: 2_500_000,
  heroes: [
    hero(4, 'Delta', {
      meta: ['ultra', 'pro', 'pub'],
      pro_picks: 40,
      pro_bans: 20,
      pro_wins: 25,
      pro_pick_ban_rate: 78.9,
      pro_win_rate: 62.5,
      pub_picks: 1_234_567,
      pub_wins: 650_000,
      pub_pick_rate: 49.4,
      pub_win_rate: 52.6,
    }),
    hero(1, 'Alpha', {
      meta: ['pro'],
      pro_bans: 30,
      pro_pick_ban_rate: 39.5,
      pub_picks: 950,
      pub_wins: 400,
      pub_pick_rate: 0.04,
      pub_win_rate: 42.1,
    }),
    hero(2, 'Beta', {
      meta: ['pub'],
      pro_picks: 2,
      pro_wins: 1,
      pro_pick_ban_rate: 2.6,
      pro_win_rate: 50,
      pub_picks: 164_200,
      pub_wins: 95_000,
      pub_pick_rate: 6.6,
      pub_win_rate: 57.9,
    }),
  ],
}

const mockFetch = (data: unknown, ok = true, status = 200) => {
  const fetchMock = vi.fn(() => Promise.resolve({ ok, status, json: () => Promise.resolve(data) }))
  globalThis.fetch = fetchMock as unknown as typeof fetch
  return fetchMock
}

const table = () => screen.getByRole('table', { name: 'Meta heroes' })
const bodyRows = () => within(table()).getAllByRole('row').slice(1)
const rows = () => bodyRows().map((r) => within(r).getAllByRole('cell').map((c) => c.textContent))
const names = () => rows().map((r) => r[0])

const DEFAULT_URL =
  '/api/heroes/meta?pro_min_pick_ban=30&ultra_min_win=55&ultra_min_picks=5&pub_top=30&pub_min_win=52'

const renderLoaded = async () => {
  const fetchMock = mockFetch(meta)
  render(<MetaTab />)
  await screen.findByRole('table', { name: 'Meta heroes' })
  return fetchMock
}

describe('formatShortCount', () => {
  it('shortens thousands and millions like OpenDota', () => {
    expect(formatShortCount(950)).toBe('950')
    expect(formatShortCount(1200)).toBe('1.2k')
    expect(formatShortCount(5000)).toBe('5k')
    expect(formatShortCount(164_200)).toBe('164k')
    expect(formatShortCount(1_234_567)).toBe('1.2M')
    expect(formatShortCount(25_000_000)).toBe('25M')
  })
})

describe('MetaTab', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('shows pro, ultra and pub meta heroes in one table with percentages and short pub picks', async () => {
    const fetchMock = await renderLoaded()

    expect(fetchMock).toHaveBeenCalledWith(DEFAULT_URL, undefined)
    expect(within(table()).getAllByRole('columnheader').map((c) => c.textContent)).toEqual([
      'Hero',
      'Meta▲',
      'Pro P+B',
      'Pro Win',
      'Pub Picks',
      'Pub Win',
    ])
    // Ultra replaces Pro for an ultra meta hero; pick and ban numbers are only in tooltips
    expect(rows()).toEqual([
      ['Delta', '★ UltraPub', '78.9%', '62.5%', '1.2M', '52.6%'],
      ['Alpha', 'Pro', '39.5%', '-', '950', '42.1%'],
      ['Beta', 'Pub', '2.6%', '50.0%', '164k', '57.9%'],
    ])
    expect(within(table()).getByRole('img', { name: 'Beta icon' })).toHaveAttribute('src', 'https://cdn/Beta.png')
    expect(screen.getByText(/76 pro matches, 2.5M Immortal, Divine and Ancient matches/)).toBeInTheDocument()
  })

  it('highlights ultra meta heroes and explains each meta tag', async () => {
    await renderLoaded()
    const [delta, alpha] = bodyRows()
    expect(delta).toHaveClass('meta-ultra')
    expect(alpha).not.toHaveClass('meta-ultra')
    expect(within(delta).getByText('★ Ultra')).toHaveAttribute(
      'title',
      'Ultra meta: pro meta with a win rate above 55% and at least 5 picks',
    )
    expect(within(alpha).getByText('Pro')).toHaveAttribute('title', 'Pro meta: Pick + Ban rate in pro matches above 30%')
    expect(within(bodyRows()[2]).getByText('Pub')).toHaveAttribute(
      'title',
      'Pub meta: of the 30 most picked Immortal, Divine and Ancient heroes, a win rate above 52%',
    )
  })

  it('shows the numbers behind each percentage in tooltips', async () => {
    await renderLoaded()
    const cells = within(bodyRows()[0]).getAllByRole('cell')
    expect(cells[2]).toHaveAttribute('title', '40 picks + 20 bans in 76 pro matches')
    expect(cells[3]).toHaveAttribute('title', '25 wins in 40 pro picks')
    expect(cells[4]).toHaveAttribute('title', '1,234,567 picks, 49.4% of 2,500,000 Imm/Div/Anc matches')
    expect(cells[5]).toHaveAttribute('title', '650,000 wins in 1,234,567 Imm/Div/Anc picks')
  })

  it('sorts by a clicked column, highest first, and reverses on a second click', async () => {
    const user = userEvent.setup()
    await renderLoaded()

    await user.click(screen.getByRole('button', { name: 'Pub Win' }))
    expect(names()).toEqual(['Beta', 'Delta', 'Alpha'])
    expect(screen.getByRole('columnheader', { name: /Pub Win/ })).toHaveAttribute('aria-sort', 'descending')

    await user.click(screen.getByRole('button', { name: /Pub Win/ }))
    expect(names()).toEqual(['Alpha', 'Delta', 'Beta'])
    expect(screen.getByRole('columnheader', { name: /Pub Win/ })).toHaveAttribute('aria-sort', 'ascending')

    // Heroes without a value go last
    await user.click(screen.getByRole('button', { name: 'Pro Win' }))
    expect(names()).toEqual(['Delta', 'Beta', 'Alpha'])
    await user.click(screen.getByRole('button', { name: /Pro Win/ }))
    expect(names()).toEqual(['Beta', 'Delta', 'Alpha'])

    // Names A to Z first
    await user.click(screen.getByRole('button', { name: 'Hero' }))
    expect(names()).toEqual(['Alpha', 'Beta', 'Delta'])
    await user.click(screen.getByRole('button', { name: 'Pub Picks' }))
    expect(names()).toEqual(['Delta', 'Beta', 'Alpha'])
  })

  it('has the settings and Refresh data below the table', async () => {
    await renderLoaded()
    const settings = screen.getByRole('form', { name: 'Meta settings' })
    expect(table().compareDocumentPosition(settings) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    for (const name of ['Apply', 'Defaults', 'Refresh data']) {
      expect(within(settings).getByRole('button', { name })).toHaveClass('check-btn')
    }
  })

  it('applies new thresholds, keeps them and resets to defaults', async () => {
    const user = userEvent.setup()
    const fetchMock = await renderLoaded()

    const pickBan = screen.getByLabelText('Pro meta: Pick + Ban % above')
    await user.clear(pickBan)
    await user.type(pickBan, '20')
    await user.click(screen.getByRole('button', { name: 'Apply' }))

    const url = '/api/heroes/meta?pro_min_pick_ban=20&ultra_min_win=55&ultra_min_picks=5&pub_top=30&pub_min_win=52'
    expect(fetchMock).toHaveBeenLastCalledWith(url, undefined)
    expect(JSON.parse(localStorage.getItem(META_PARAMS_KEY) ?? '{}')).toMatchObject({
      pro_min_pick_ban: 20,
    })

    await user.click(screen.getByRole('button', { name: 'Defaults' }))
    expect(fetchMock).toHaveBeenLastCalledWith(DEFAULT_URL, undefined)
    expect(localStorage.getItem(META_PARAMS_KEY)).toBeNull()
    expect(screen.getByLabelText('Pro meta: Pick + Ban % above')).toHaveValue(30)
  })

  it('refreshes the hero stats from OpenDota with the current thresholds', async () => {
    const user = userEvent.setup()
    const fetchMock = await renderLoaded()

    fetchMock.mockImplementation(() =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ ...meta, pro_matches: 80 }) }),
    )
    await user.click(screen.getByRole('button', { name: 'Refresh data' }))
    expect(fetchMock).toHaveBeenLastCalledWith(`${DEFAULT_URL}&refresh=true`, undefined)
    expect(await screen.findByText(/80 pro matches/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh data' })).toBeEnabled()
  })

  it('loads saved thresholds', async () => {
    localStorage.setItem(META_PARAMS_KEY, JSON.stringify({ pub_top: 10, pub_bracket: 7 }))
    const fetchMock = await renderLoaded()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/heroes/meta?pro_min_pick_ban=30&ultra_min_win=55&ultra_min_picks=5&pub_top=10&pub_min_win=52',
      undefined,
    )
    expect(screen.getByLabelText('Pub meta: most picked heroes')).toHaveValue(10)
  })

  it('shows an empty list and errors', async () => {
    mockFetch({ ...meta, heroes: [] })
    const { unmount } = render(<MetaTab />)
    expect(await screen.findByText('No heroes match these thresholds.')).toBeInTheDocument()
    unmount()

    mockFetch({ message: 'Failed to fetch hero stats from OpenDota' }, false, 503)
    render(<MetaTab />)
    expect(await screen.findByText('Meta: Failed to fetch hero stats from OpenDota')).toBeInTheDocument()
  })
})

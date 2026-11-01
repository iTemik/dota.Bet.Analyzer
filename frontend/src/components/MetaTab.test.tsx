import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Meta } from '../types'
import { DEFAULT_META_PARAMS, META_PARAMS_KEY } from '../meta'
import MetaTab from './MetaTab'

const hero = (hero_id: number, name: string) => ({
  hero_id,
  localized_name: name,
  icon: `https://cdn/${name}.png`,
})

const meta: Meta = {
  fetched_at: 1_800_000_000,
  params: DEFAULT_META_PARAMS,
  pro_matches: 76,
  pub_matches: 1000,
  pro_meta: [
    { ...hero(4, 'Delta'), picks: 40, bans: 20, wins: 25, pick_ban_rate: 78.9, win_rate: 62.5 },
    { ...hero(1, 'Alpha'), picks: 0, bans: 30, wins: 0, pick_ban_rate: 39.5, win_rate: null },
  ],
  ultra_meta: [{ ...hero(4, 'Delta'), picks: 40, bans: 20, wins: 25, pick_ban_rate: 78.9, win_rate: 62.5 }],
  pub_meta: [{ ...hero(2, 'Beta'), picks: 500, wins: 290, pick_rate: 50, win_rate: 58 }],
}

const mockFetch = (data: unknown, ok = true, status = 200) => {
  const fetchMock = vi.fn(() => Promise.resolve({ ok, status, json: () => Promise.resolve(data) }))
  globalThis.fetch = fetchMock as unknown as typeof fetch
  return fetchMock
}

const rows = (label: string) =>
  within(screen.getByRole('table', { name: label }))
    .getAllByRole('row')
    .slice(1)
    .map((r) => within(r).getAllByRole('cell').map((c) => c.textContent))

const DEFAULT_URL =
  '/api/heroes/meta?pro_min_pick_ban=30&ultra_min_win=55&ultra_min_picks=5&pub_top=30'

describe('MetaTab', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('shows pro, ultra and pub meta tables', async () => {
    const fetchMock = mockFetch(meta)
    render(<MetaTab />)

    await screen.findByRole('heading', { name: 'Pro Meta' })
    expect(fetchMock).toHaveBeenCalledWith(DEFAULT_URL, undefined)
    expect(rows('Pro meta')).toEqual([
      ['Delta', '78.9%', '40', '20', '62.5%'],
      ['Alpha', '39.5%', '0', '30', '-'],
    ])
    expect(rows('Ultra meta')).toEqual([['Delta', '78.9%', '40', '20', '62.5%']])
    expect(rows('Pub meta')).toEqual([['Beta', '58.0%', '50.0%', '500']])
    expect(within(screen.getByRole('table', { name: 'Pub meta' })).getByRole('img', { name: 'Beta icon' })).toHaveAttribute(
      'src',
      'https://cdn/Beta.png',
    )
    expect(screen.getByText(/76 pro matches/)).toBeInTheDocument()
    expect(screen.getByText('Pick + Ban rate in pro matches above 30%.')).toBeInTheDocument()
    expect(
      screen.getByText('Pro meta heroes with a win rate above 55% and at least 5 picks.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        "Top 30 heroes by win rate in Immortal, Divine and Ancient games (1000 matches), like OpenDota's Imm/Div/Anc W%.",
      ),
    ).toBeInTheDocument()
  })

  it('applies new thresholds, keeps them and resets to defaults', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch(meta)
    render(<MetaTab />)
    await screen.findByRole('heading', { name: 'Pro Meta' })

    const pickBan = screen.getByLabelText('Pro meta: Pick + Ban % above')
    await user.clear(pickBan)
    await user.type(pickBan, '20')
    await user.click(screen.getByRole('button', { name: 'Apply' }))

    const url = '/api/heroes/meta?pro_min_pick_ban=20&ultra_min_win=55&ultra_min_picks=5&pub_top=30'
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
    const fetchMock = mockFetch(meta)
    render(<MetaTab />)
    await screen.findByRole('heading', { name: 'Pro Meta' })

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
    const fetchMock = mockFetch(meta)
    render(<MetaTab />)
    await screen.findByRole('heading', { name: 'Pro Meta' })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/heroes/meta?pro_min_pick_ban=30&ultra_min_win=55&ultra_min_picks=5&pub_top=10',
      undefined,
    )
    expect(screen.getByLabelText('Pub meta: top heroes')).toHaveValue(10)
  })

  it('shows empty lists and errors', async () => {
    mockFetch({ ...meta, pro_meta: [], ultra_meta: [], pub_meta: [] })
    const { unmount } = render(<MetaTab />)
    expect(await screen.findAllByText('No heroes match these thresholds.')).toHaveLength(2)
    expect(screen.getByText('No pub games in this bracket.')).toBeInTheDocument()
    unmount()

    mockFetch({ message: 'Failed to fetch hero stats from OpenDota' }, false, 503)
    render(<MetaTab />)
    expect(await screen.findByText('Meta: Failed to fetch hero stats from OpenDota')).toBeInTheDocument()
  })
})

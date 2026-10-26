import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Matches } from '../types'
import MatchesTables, { MATCHES_PAGE_SIZE } from './MatchesTables'

const mockFetch = (data: unknown, ok = true, status = 200) => {
  const fetchMock = vi.fn(() => Promise.resolve({ ok, status, json: () => Promise.resolve(data) }))
  globalThis.fetch = fetchMock as unknown as typeof fetch
  return fetchMock
}

const alpha = { name: 'Team Alpha', team_id: 11, logo_url: 'https://logo/alpha.png' }
const beta = { name: 'Beta Squad', team_id: null, logo_url: null }
const tbd = { name: 'TBD', team_id: null, logo_url: null }

const matches: Matches = {
  upcoming: [
    { start_time: 1_800_003_600, best_of: 3, team1: alpha, team2: beta },
    { start_time: 1_800_009_000, best_of: null, team1: tbd, team2: tbd },
  ],
  finished: [
    { start_time: 1_799_990_000, best_of: 3, team1: beta, team2: alpha, score1: 2, score2: 1 },
    { start_time: 1_799_980_000, best_of: null, team1: alpha, team2: beta, score1: 0, score2: 2 },
  ],
}

const table = (heading: string) => screen.getByRole('heading', { name: heading }).nextElementSibling as HTMLElement

describe('MatchesTables', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('shows upcoming and finished series with Bo, icons and scores', async () => {
    const fetchMock = mockFetch(matches)
    render(<MatchesTables onSelect={vi.fn()} />)

    await screen.findByRole('heading', { name: 'Upcoming Matches' })
    expect(fetchMock).toHaveBeenCalledWith('/api/matches', undefined)

    const upcoming = within(table('Upcoming Matches')).getAllByRole('row').slice(1)
    expect(upcoming).toHaveLength(2)
    const cells = within(upcoming[0]).getAllByRole('cell').map((c) => c.textContent)
    expect(cells.slice(1)).toEqual(['Bo3', '', 'Team Alpha', '', 'Beta Squad'])
    expect(cells[0]).toMatch(/^[A-Z][a-z]{2} \d+/)
    expect(within(upcoming[0]).getByRole('img', { name: 'Team Alpha logo' })).toHaveAttribute('src', alpha.logo_url)
    expect(within(upcoming[0]).queryByRole('img', { name: 'Beta Squad logo' })).not.toBeInTheDocument()

    const finished = within(table('Finished Matches')).getAllByRole('row').slice(1)
    expect(finished.map((r) => r.lastElementChild?.textContent)).toEqual(['2:1', '0:2'])
    expect(within(finished[1]).getAllByRole('cell')[1]).toHaveTextContent('-')
    expect(screen.getByRole('link', { name: 'Liquipedia' })).toHaveAttribute(
      'href',
      'https://liquipedia.net/dota2/Liquipedia:Matches',
    )
  })

  it('calls onSelect with a clicked upcoming series, finished and TBD rows are not clickable', async () => {
    mockFetch(matches)
    const onSelect = vi.fn()
    render(<MatchesTables onSelect={onSelect} />)

    await userEvent.click(await screen.findByText('Bo3', { selector: '.match-row-clickable td' }))
    expect(onSelect).toHaveBeenCalledWith(matches.upcoming[0])

    await userEvent.click(within(table('Finished Matches')).getByText('2:1'))
    await userEvent.click(within(table('Upcoming Matches')).getAllByText('TBD')[0])
    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(within(table('Upcoming Matches')).getAllByRole('row')[2]).not.toHaveClass('match-row-clickable')
  })

  it('shows 10 matches per page with Previous and Next buttons', async () => {
    const many = Array.from({ length: 23 }, (_, i) => ({
      start_time: 1_800_000_000 + i * 3600,
      best_of: 3,
      team1: { ...alpha, name: `Team ${i}` },
      team2: beta,
    }))
    mockFetch({ upcoming: many, finished: matches.finished })
    render(<MatchesTables onSelect={vi.fn()} />)

    const upcomingTable = await screen.findByRole('table', { name: 'Upcoming matches' })
    const names = () => within(upcomingTable).getAllByRole('row').slice(1).map((r) => r.children[3].textContent)
    expect(MATCHES_PAGE_SIZE).toBe(10)
    expect(names()).toHaveLength(10)
    expect(names()[0]).toBe('Team 0')
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()

    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('Page 3 of 3')).toBeInTheDocument()
    expect(names()).toEqual(['Team 20', 'Team 21', 'Team 22'])
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()

    // The finished table has a single page, so no buttons of its own
    expect(screen.getAllByRole('button', { name: 'Next' })).toHaveLength(1)
  })

  it('says when there are no matches', async () => {
    mockFetch({ upcoming: [], finished: [] })
    render(<MatchesTables onSelect={vi.fn()} />)

    expect(await screen.findByText('No upcoming matches.')).toBeInTheDocument()
    expect(screen.getByText('No finished matches.')).toBeInTheDocument()
  })

  it('shows the backend error', async () => {
    mockFetch({ message: 'Failed to fetch matches from Liquipedia' }, false, 503)
    render(<MatchesTables onSelect={vi.fn()} />)

    expect(await screen.findByText('Matches: Failed to fetch matches from Liquipedia')).toBeInTheDocument()
  })
})

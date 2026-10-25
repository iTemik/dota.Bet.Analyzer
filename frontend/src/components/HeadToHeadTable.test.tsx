import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { HeadToHead } from '../types'
import HeadToHeadTable from './HeadToHeadTable'

const mockFetch = (data: unknown, ok = true, status = 200) => {
  const fetchMock = vi.fn(() => Promise.resolve({ ok, status, json: () => Promise.resolve(data) }))
  globalThis.fetch = fetchMock as unknown as typeof fetch
  return fetchMock
}

const headToHead: HeadToHead = {
  since: 1_760_000_000,
  matches: [
    { match_id: 8003, start_time: 1_761_000_000, team1_won: false, before_prediction: false },
    { match_id: 8002, start_time: 1_760_900_000, team1_won: true, before_prediction: true },
    { match_id: 8001, start_time: 1_760_800_000, team1_won: null, before_prediction: true },
  ],
}

describe('HeadToHeadTable', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('lists matches with OpenDota links, results and a tag on matches before the prediction', async () => {
    const fetchMock = mockFetch(headToHead)
    render(<HeadToHeadTable predictionId={7} teamNames={['Team A', 'Team B']} />)

    const link = await screen.findByRole('link', { name: '8003' })
    expect(fetchMock).toHaveBeenCalledWith('/api/predictions/7/head-to-head', undefined)
    expect(link).toHaveAttribute('href', 'https://www.opendota.com/matches/8003')
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows.map((r) => r.lastElementChild?.textContent)).toEqual(['Team B won', 'Team A won', 'unknown'])
    expect(rows[0]).not.toHaveTextContent('before prediction')
    expect(rows[1]).toHaveTextContent('before prediction')
    expect(rows[1]).toHaveClass('before-prediction')
  })

  it('says when the teams have not played each other', async () => {
    mockFetch({ since: 1_760_000_000, matches: [] })
    render(<HeadToHeadTable predictionId={7} teamNames={['Team A', 'Team B']} />)

    expect(await screen.findByText(/No matches between these teams since/)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows the backend error', async () => {
    mockFetch({ message: 'Failed to read predictions from database' }, false, 500)
    render(<HeadToHeadTable predictionId={7} teamNames={['Team A', 'Team B']} />)

    expect(await screen.findByText('Failed to read predictions from database')).toBeInTheDocument()
  })
})

import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { formatDate } from '../format'
import TeamsSync, { STATUS_POLL_MS } from './TeamsSync'

const jsonResponse = (data: unknown, status = 200) =>
  Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(data) })

const SYNCED_AT = 1760000000

// GET returns the given statuses in order (the last one repeats), POST returns postResponse
const mockApi = (statuses: unknown[], postResponse?: ReturnType<typeof jsonResponse>) => {
  let call = 0
  const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
    if (init?.method === 'POST') return postResponse
    return jsonResponse(statuses[Math.min(call++, statuses.length - 1)])
  })
  globalThis.fetch = fetchMock as unknown as typeof fetch
  return fetchMock
}

describe('TeamsSync', () => {
  beforeEach(() => vi.clearAllMocks())
  afterEach(() => vi.useRealTimers())

  it('shows when the teams list was last updated', async () => {
    const fetchMock = mockApi([{ synced_at: SYNCED_AT, running: false }])
    render(<TeamsSync />)
    expect(await screen.findByText(`Updated ${formatDate(SYNCED_AT)}`)).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/teams/sync', undefined)
    expect(screen.getByRole('button', { name: 'Update teams data' })).toBeEnabled()
  })

  it('says when the teams list was never updated', async () => {
    mockApi([{ synced_at: null, running: false }])
    render(<TeamsSync />)
    expect(await screen.findByText('Never updated')).toBeInTheDocument()
  })

  it('runs the sync and shows the result', async () => {
    let resolvePost: (value: unknown) => void = () => {}
    const post = new Promise((resolve) => (resolvePost = resolve))
    const fetchMock = mockApi([{ synced_at: null, running: false }], post as ReturnType<typeof jsonResponse>)
    render(<TeamsSync />)
    await screen.findByText('Never updated')

    await userEvent.click(screen.getByRole('button', { name: 'Update teams data' }))
    expect(fetchMock).toHaveBeenCalledWith('/api/teams/sync', { method: 'POST' })
    expect(screen.getByRole('button', { name: 'Updating teams…' })).toBeDisabled()

    await act(async () =>
      resolvePost(await jsonResponse({ synced_count: 21654, message: 'Stored 21654 teams', synced_at: SYNCED_AT })),
    )
    expect(screen.getByRole('status')).toHaveTextContent('Stored 21654 teams')
    expect(screen.getByText(`Updated ${formatDate(SYNCED_AT)}`)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Update teams data' })).toBeEnabled()
  })

  it('shows the error when the sync fails', async () => {
    mockApi(
      [{ synced_at: null, running: false }],
      jsonResponse({ status: 503, code: 'FAILED_TO_FETCH_TEAMS', message: 'Failed to fetch teams from API' }, 503),
    )
    render(<TeamsSync />)
    await screen.findByText('Never updated')
    await userEvent.click(screen.getByRole('button', { name: 'Update teams data' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Failed to fetch teams from API')
    expect(screen.getByRole('status')).toHaveClass('teams-sync-error')
  })

  it('waits for a running startup sync before enabling the button', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mockApi([
      { synced_at: null, running: true },
      { synced_at: SYNCED_AT, running: false },
    ])
    render(<TeamsSync />)
    expect(await screen.findByRole('button', { name: 'Updating teams…' })).toBeDisabled()

    await act(async () => vi.advanceTimersByTimeAsync(STATUS_POLL_MS))
    expect(await screen.findByRole('button', { name: 'Update teams data' })).toBeEnabled()
    expect(screen.getByText(`Updated ${formatDate(SYNCED_AT)}`)).toBeInTheDocument()
  })
})

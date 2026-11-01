import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { type DataStatus as Status, type JobStatus, parseDataStatus } from '../dataStatus'
import DataStatus from './DataStatus'

const job = (name: string, title: string, extra: Partial<JobStatus> = {}): JobStatus => ({
  name,
  title,
  state: 'idle',
  progress: 100,
  message: null,
  last_success: 1_800_000_000,
  last_error: null,
  last_error_at: null,
  next_run: 1_800_086_400,
  ...extra,
})

const status = (jobs: JobStatus[], used: number | null = 340, limit = 1800): Status => ({
  jobs,
  budget: { used, limit },
})

const idleJobs = () => [job('teams', 'Teams list'), job('heroes', 'Heroes', { last_success: null, next_run: null })]

// The stream answers with the given lines; POST /api/jobs/{name}/run answers with `runAnswer`
const mockFetch = (lines: unknown[], runAnswer?: { ok: boolean; status: number; data: unknown }) => {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      const answer = runAnswer ?? { ok: true, status: 202, data: {} }
      return Promise.resolve({ ok: answer.ok, status: answer.status, json: () => Promise.resolve(answer.data) })
    }
    if (url === '/api/jobs/stream') {
      const text = lines.map((line) => (typeof line === 'string' ? line : JSON.stringify(line))).join('\n')
      return Promise.resolve({ ok: true, status: 200, body: null, text: () => Promise.resolve(text) })
    }
    return Promise.reject(new Error(`unexpected ${url}`))
  })
  globalThis.fetch = fetchMock as unknown as typeof fetch
  return fetchMock
}

const summary = () => screen.getByTestId('data-status-summary')

afterEach(() => {
  vi.restoreAllMocks()
})

describe('parseDataStatus', () => {
  it('reads status lines and skips error and invalid lines', () => {
    expect(parseDataStatus(JSON.stringify(status([])))).toEqual(status([]))
    expect(parseDataStatus('{"error": "disk"}')).toBeNull()
    expect(parseDataStatus('not json')).toBeNull()
  })
})

describe('DataStatus', () => {
  it('shows nothing until the stream sends a status', async () => {
    const fetchMock = mockFetch(['{"error": "disk"}'])
    const { container } = render(<DataStatus />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/jobs/stream', expect.anything()))
    expect(container).toBeEmptyDOMElement()
  })

  it('shows "Data up to date" with each job\'s last update on hover', async () => {
    mockFetch([status(idleJobs())])
    render(<DataStatus />)
    expect(await screen.findByText('Data up to date')).toBeInTheDocument()
    expect(summary().title).toMatch(/^Teams list: .+\nHeroes: never$/)
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
  })

  it('shows the OpenDota budget with a bar', async () => {
    mockFetch([status(idleJobs())])
    render(<DataStatus />)
    expect(await screen.findByText('OpenDota today: 340 / 1800')).toBeInTheDocument()
    const bar = screen.getByRole('progressbar', { name: 'OpenDota requests today' })
    expect(bar).toHaveAttribute('aria-valuenow', '340')
    expect(screen.getByTestId('data-budget')).not.toHaveClass('data-budget-warn')
  })

  it('turns the budget red near the daily limit', async () => {
    mockFetch([status(idleJobs(), 1700)])
    render(<DataStatus />)
    expect(await screen.findByText('OpenDota today: 1700 / 1800')).toBeInTheDocument()
    expect(screen.getByTestId('data-budget')).toHaveClass('data-budget-warn')
  })

  it('shows only the count when there is no daily budget', async () => {
    mockFetch([status(idleJobs(), 340, 0)])
    render(<DataStatus />)
    expect(await screen.findByText('OpenDota today: 340')).toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('hides the budget when Redis cannot count requests', async () => {
    mockFetch([status(idleJobs(), null)])
    render(<DataStatus />)
    await screen.findByText('Data up to date')
    expect(screen.queryByTestId('data-budget')).not.toBeInTheDocument()
  })

  it('shows the running job with its progress, from the latest line', async () => {
    mockFetch([
      status(idleJobs()),
      status([job('teams', 'Teams list', { state: 'running', progress: 40, message: 'Updating teams list' })]),
    ])
    render(<DataStatus />)
    expect(await screen.findByText('Updating teams list 40%')).toBeInTheDocument()
  })

  it('shows a wait for the request limit', async () => {
    const message = 'Updating teams list: waiting for the request limit, 12 s'
    mockFetch([status([job('teams', 'Teams list', { state: 'running', progress: 0, message })])])
    render(<DataStatus />)
    expect(await screen.findByText(message)).toBeInTheDocument()
  })

  it('shows a failed job in red and retries it', async () => {
    const failed = job('teams', 'Teams list', { state: 'failed', last_error: 'OpenDota down' })
    const queued = job('teams', 'Teams list', { state: 'queued', progress: 0, message: 'Teams list update queued' })
    const fetchMock = mockFetch([status([failed, job('heroes', 'Heroes')])], { ok: true, status: 202, data: queued })
    render(<DataStatus />)
    expect(await screen.findByText('Teams list update failed')).toHaveClass('data-status-failed')

    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(fetchMock).toHaveBeenCalledWith('/api/jobs/teams/run', { method: 'POST' })
    expect(await screen.findByText('Teams list update queued')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
  })

  it('lists every job in the details panel with a Run button', async () => {
    const running = job('teams', 'Teams list', { state: 'running', progress: 0, message: 'Updating teams list' })
    const fetchMock = mockFetch([status([running, job('heroes', 'Heroes', { message: 'Stored 120 heroes' })])])
    render(<DataStatus />)
    await userEvent.click(await screen.findByRole('button', { name: 'Details' }))

    const rows = within(screen.getByRole('table', { name: 'Data jobs' })).getAllByRole('row').slice(1)
    expect(rows.map((row) => within(row).getAllByRole('cell').slice(0, 2).map((c) => c.textContent))).toEqual([
      ['Teams list', 'Updating teams list'],
      ['Heroes', 'Stored 120 heroes'],
    ])
    expect(screen.getByRole('button', { name: 'Run Teams list' })).toBeDisabled()

    await userEvent.click(screen.getByRole('button', { name: 'Run Heroes' }))
    expect(fetchMock).toHaveBeenCalledWith('/api/jobs/heroes/run', { method: 'POST' })

    await userEvent.click(screen.getByRole('button', { name: 'Hide details' }))
    expect(screen.queryByRole('table', { name: 'Data jobs' })).not.toBeInTheDocument()
  })

  it('shows why a job could not be started', async () => {
    mockFetch([status(idleJobs())], {
      ok: false,
      status: 409,
      data: { message: 'Job is already queued or running' },
    })
    render(<DataStatus />)
    await userEvent.click(await screen.findByRole('button', { name: 'Details' }))
    await userEvent.click(screen.getByRole('button', { name: 'Run Heroes' }))
    expect(await screen.findByText('Job is already queued or running')).toBeInTheDocument()
  })
})

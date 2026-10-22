import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { prediction } from '../test/predictionFixtures'
import PredictionList from './PredictionList'

const jsonResponse = (data: unknown, ok = true, status = ok ? 200 : 500) =>
  Promise.resolve({ ok, status, json: () => Promise.resolve(data) })

const predictions = [
  prediction({ prediction_id: 3 }),
  prediction({ prediction_id: 2, bet_team: null, stake: null, team1_maps_won: 1, team2_maps_won: 2 }),
  prediction({ prediction_id: 1, best_of: 5, team1_maps_won: 3, team2_maps_won: 1, bet_won: true }),
]

const mockList = (response = jsonResponse(predictions)) => {
  const fetchMock = vi.fn(() => response)
  globalThis.fetch = fetchMock as unknown as typeof fetch
  return fetchMock
}

const rows = () => screen.getAllByRole('row').slice(1)

describe('PredictionList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.location.hash = '#predictions'
  })

  it('lists the predictions with odds, series, bet, result and outcome', async () => {
    const fetchMock = mockList()
    render(<PredictionList />)
    await screen.findByRole('table')
    expect(fetchMock).toHaveBeenCalledWith('/api/predictions', undefined)
    expect(rows()).toHaveLength(3)

    const pending = within(rows()[0])
    expect(pending.getByRole('link')).toHaveAttribute('href', '#predictions/3')
    expect(pending.getByRole('link')).toHaveTextContent(/Team A\s*vs\s*Team B/)
    expect(pending.getByText('1.85 / 2.05')).toBeInTheDocument()
    expect(pending.getByText('bo3')).toBeInTheDocument()
    expect(pending.getByText('Team A · 100')).toBeInTheDocument()
    expect(pending.getByText('pending')).toBeInTheDocument()
    expect(pending.getByText('Pending')).toBeInTheDocument()

    expect(within(rows()[1]).getAllByText('No bet')).toHaveLength(2)
    expect(within(rows()[1]).getByText('1-2')).toBeInTheDocument()
    expect(within(rows()[2]).getByText('Won')).toHaveClass('outcome-won')
  })

  it('shows totals and filters pending and settled predictions', async () => {
    mockList()
    render(<PredictionList />)
    expect(await screen.findByText('Bets: 2 · Won: 1 · Lost: 0 · Pending: 1')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Settled' }))
    expect(rows()).toHaveLength(2)
    expect(screen.getByText('Bets: 1 · Won: 1 · Lost: 0 · Pending: 0')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Pending' }))
    expect(rows()).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Pending' })).toHaveAttribute('aria-pressed', 'true')

    await userEvent.click(screen.getByRole('button', { name: 'All' }))
    expect(rows()).toHaveLength(3)
  })

  it('opens a prediction when its row is clicked', async () => {
    mockList()
    render(<PredictionList />)
    await screen.findByRole('table')
    await userEvent.click(within(rows()[2]).getByText('bo5'))
    expect(window.location.hash).toBe('#predictions/1')
  })

  it('says when there are no predictions yet', async () => {
    mockList(jsonResponse([]))
    render(<PredictionList />)
    expect(await screen.findByText(/No predictions yet/)).toBeInTheDocument()
  })

  it('shows an error when the list fails to load', async () => {
    mockList(jsonResponse({ message: 'Database is locked' }, false))
    render(<PredictionList />)
    expect(await screen.findByText(/Failed to load predictions: Database is locked/)).toBeInTheDocument()
  })
})

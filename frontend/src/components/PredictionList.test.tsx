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

  it('lists the predictions like the Finished Matches table, then odds, bet and outcome', async () => {
    const fetchMock = mockList()
    render(<PredictionList />)
    await screen.findByRole('table')
    expect(fetchMock).toHaveBeenCalledWith('/api/predictions', undefined)
    expect(rows()).toHaveLength(3)

    const pending = within(rows()[0])
    expect(pending.getByRole('link')).toHaveAttribute('href', '#predictions/3')
    expect(pending.getByRole('link').textContent).toMatch(/^[A-Z][a-z]{2} \d+/)
    const cells = pending.getAllByRole('cell').map((c) => c.textContent)
    expect(cells.slice(1)).toEqual(['Bo3', '', 'Team A', '', 'Team B', '-', '1.85 / 2.05', 'Team A · 100', 'Pending +185 / -100'])

    expect(within(rows()[1]).getAllByText('No bet')).toHaveLength(2)
    expect(within(rows()[1]).getByText('1:2')).toBeInTheDocument()
    expect(pending.getByText('+185')).toHaveClass('money-profit')
    expect(pending.getByText('-100')).toHaveClass('money-loss')
    const won = within(rows()[2]).getAllByRole('cell').at(-1)
    expect(won).toHaveClass('outcome-won')
    expect(won).toHaveTextContent('Won +185')
  })

  it('shows totals and filters pending and settled predictions', async () => {
    mockList()
    render(<PredictionList />)
    await screen.findByRole('table')
    const totals = () => document.querySelector<HTMLElement>('.prediction-totals')!
    expect(totals()).toHaveTextContent('Bets: 2 · Won: 1 · Lost: 0 · Pending: 1 · Possible profit: +370 · Possible loss: -100 Simulation: not real money')
    expect(within(totals()).getByText('+370')).toHaveClass('money-profit')
    expect(within(totals()).getByText('-100')).toHaveClass('money-loss')
    expect(within(totals()).getByText('+370')).toHaveAttribute('title', 'Simulation: not real money')

    await userEvent.click(screen.getByRole('button', { name: 'Settled' }))
    expect(rows()).toHaveLength(2)
    expect(totals()).toHaveTextContent('Bets: 1 · Won: 1 · Lost: 0 · Pending: 0 · Possible profit: +185 · Possible loss: 0 Simulation: not real money')

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
    await userEvent.click(within(rows()[2]).getByText('Bo5'))
    expect(window.location.hash).toBe('#predictions/1')
  })

  it('shows 10 predictions per page', async () => {
    mockList(jsonResponse(Array.from({ length: 12 }, (_, i) => prediction({ prediction_id: 100 - i }))))
    render(<PredictionList />)
    await screen.findByRole('table')
    expect(rows()).toHaveLength(10)
    expect(screen.getByText('Page 1 of 2')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(rows()).toHaveLength(2)
    expect(within(rows()[0]).getByRole('link')).toHaveAttribute('href', '#predictions/90')

    // A filter starts again from the first page
    await userEvent.click(screen.getByRole('button', { name: 'Pending' }))
    expect(screen.getByText('Page 1 of 2')).toBeInTheDocument()
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

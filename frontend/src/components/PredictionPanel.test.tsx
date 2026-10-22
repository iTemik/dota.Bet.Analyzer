import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { StatisticsResult, TeamData } from '../types'
import PredictionPanel from './PredictionPanel'

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

const teams = [
  team({ team: 'Team A', team_id: 1, task_id: 'task_a', latest_match_time: 100 }),
  team({ team: 'Team B', team_id: 2, task_id: 'task_b' }),
]

const result = (avgRank: number): StatisticsResult => ({
  results: [
    { account_id: 11, match_count: 30, rank: 45 },
    { account_id: 12, error: 'boom' },
  ],
  summary: {
    rating_matches: 10,
    tournament_matches: 5,
    other_matches: 1,
    matches_median: 4,
    matches_avg: 5,
    win_percentage: 50,
    rating_win_percentage: 50,
    tournament_win_percentage: 60,
    avg_rank: avgRank,
    bad_rank_players: 0,
  },
})

const results = [result(45), result(120)]

const jsonResponse = (data: unknown, ok = true, status = ok ? 201 : 500) =>
  Promise.resolve({ ok, status, json: () => Promise.resolve(data) })

// Fetch mock that answers snapshot POSTs with ids 7 and 8 (in body order) and the prediction POST with id 3
const mockBackend = (predictionResponse = jsonResponse({ prediction_id: 3 })) => {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url === '/api/snapshots') {
      const body = JSON.parse(init?.body as string)
      return jsonResponse({ snapshot_id: body.team_id === 1 ? 7 : 8 })
    }
    if (url === '/api/predictions') return predictionResponse
    return Promise.reject(new Error(`Unexpected URL ${url}`))
  })
  globalThis.fetch = fetchMock as unknown as typeof fetch
  return fetchMock
}

const postedBodies = (fetchMock: ReturnType<typeof mockBackend>, url: string) =>
  fetchMock.mock.calls.filter(([u]) => u === url).map(([, init]) => JSON.parse((init as RequestInit).body as string))

const bookmakerBox = () => screen.getByRole('group', { name: 'From bookmaker' })
const fillOdds = async (odds1: string, odds2: string) => {
  const [input1, input2] = within(bookmakerBox()).getAllByRole('textbox')
  await userEvent.type(input1, odds1)
  await userEvent.type(input2, odds2)
}

describe('PredictionPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('is disabled until the summaries of both teams arrive', () => {
    render(<PredictionPanel teams={teams} results={[results[0], undefined]} days={20} />)
    expect(screen.getByText(/Available once the player statistics/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save prediction' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Save snapshots only' })).toBeDisabled()
  })

  it('keeps the bookmaker inputs in their own labelled box', () => {
    render(<PredictionPanel teams={teams} results={results} days={20} />)
    const box = within(bookmakerBox())
    expect(box.getByText('Coefficient Team A')).toBeInTheDocument()
    expect(box.getByText('Coefficient Team B')).toBeInTheDocument()
    const series = box.getByRole('combobox')
    expect(series).toHaveValue('3')
    expect(within(series).getAllByRole('option').map((o) => o.textContent)).toEqual(['bo1', 'bo2', 'bo3', 'bo5', 'n/a'])
    // The decision is outside the bookmaker box
    expect(box.queryByText('Bet on')).not.toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'My decision' })).toHaveTextContent('Bet on')
  })

  it('shows validation messages and sends nothing when odds or stake are invalid', async () => {
    const fetchMock = mockBackend()
    render(<PredictionPanel teams={teams} results={results} days={20} />)

    await fillOdds('1', 'abc')
    await userEvent.click(screen.getByLabelText('Team A'))
    await userEvent.click(screen.getByRole('button', { name: 'Save prediction' }))

    expect(screen.getAllByText('Must be a number above 1')).toHaveLength(2)
    expect(screen.getByText('Required with a bet')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('saves both snapshots, then the prediction, and links to it', async () => {
    const fetchMock = mockBackend()
    render(<PredictionPanel teams={teams} results={results} days={20} />)

    await fillOdds('1,85', '2.05')
    await userEvent.selectOptions(within(bookmakerBox()).getByRole('combobox'), 'bo5')
    await userEvent.click(screen.getByLabelText('Team B'))
    await userEvent.type(screen.getByLabelText('Stake'), '100')
    await userEvent.type(screen.getByLabelText('Comment'), 'Team B has a stable core')
    await userEvent.click(screen.getByRole('button', { name: 'Save prediction' }))

    const link = await screen.findByRole('link', { name: '#3' })
    expect(link).toHaveAttribute('href', '#predictions/3')
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(['/api/snapshots', '/api/snapshots', '/api/predictions'])

    const [snapshot1, snapshot2] = postedBodies(fetchMock, '/api/snapshots')
    expect(snapshot1).toEqual({
      team_id: 1,
      days: 20,
      team: { ...teams[0], task_id: undefined },
      summary: results[0].summary,
      players: [{ account_id: 11, rank: 45, match_count: 30 }],
    })
    expect(snapshot1.team).not.toHaveProperty('task_id')
    expect(snapshot2.team_id).toBe(2)
    expect(snapshot2.summary.avg_rank).toBe(120)

    expect(postedBodies(fetchMock, '/api/predictions')).toEqual([
      {
        team1_snapshot_id: 7,
        team2_snapshot_id: 8,
        team1_odds: 1.85,
        team2_odds: 2.05,
        best_of: 5,
        bet_team: 2,
        stake: 100,
        comment: 'Team B has a stable core',
      },
    ])
    // Saved once: the button stays off until the form changes
    expect(screen.getByRole('button', { name: 'Save prediction' })).toBeDisabled()
  })

  it('sends a prediction without a bet and an unknown series as nulls', async () => {
    const fetchMock = mockBackend()
    render(<PredictionPanel teams={teams} results={results} days={20} />)

    await fillOdds('1.5', '2.5')
    await userEvent.selectOptions(within(bookmakerBox()).getByRole('combobox'), 'n/a')
    expect(screen.getByLabelText('Stake')).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Save prediction' }))

    await screen.findByText(/Prediction saved/)
    expect(postedBodies(fetchMock, '/api/predictions')[0]).toMatchObject({ best_of: null, bet_team: null, stake: null })
  })

  it('saves only the snapshots', async () => {
    const fetchMock = mockBackend()
    render(<PredictionPanel teams={teams} results={results} days={20} />)

    await userEvent.click(screen.getByRole('button', { name: 'Save snapshots only' }))

    expect(await screen.findByText('Snapshots saved: #7, #8')).toBeInTheDocument()
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(['/api/snapshots', '/api/snapshots'])
  })

  it('shows the backend message when a request fails', async () => {
    mockBackend(jsonResponse({ message: 'Snapshot not found' }, false, 404))
    render(<PredictionPanel teams={teams} results={results} days={20} />)

    await fillOdds('1.5', '2.5')
    await userEvent.click(screen.getByRole('button', { name: 'Save prediction' }))

    await waitFor(() => expect(screen.getByText('Snapshot not found')).toBeInTheDocument())
    expect(screen.queryByText(/Prediction saved/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save prediction' })).toBeEnabled()
  })
})

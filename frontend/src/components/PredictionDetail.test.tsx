import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { prediction, predictionDetail } from '../test/predictionFixtures'
import type { PredictionDetail as Detail } from '../types'
import PredictionDetail from './PredictionDetail'

const jsonResponse = (data: unknown, ok = true, status = ok ? 200 : 422) =>
  Promise.resolve({ ok, status, json: () => Promise.resolve(data) })

// Fetch mock: GET returns the detail, PATCH, PUT and DELETE return the given responses (PATCH and PUT echo the body)
const mockBackend = (
  detail: Detail = predictionDetail(),
  patchResponse?: ReturnType<typeof jsonResponse>,
  deleteResponse = Promise.resolve({ ok: true, status: 204, json: () => Promise.reject(new Error('no body')) }),
  putResponse?: ReturnType<typeof jsonResponse>,
) => {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === 'PATCH') {
      const body = JSON.parse(init.body as string)
      return patchResponse ?? jsonResponse(prediction({ ...body, bet_won: body.team1_maps_won > body.team2_maps_won }))
    }
    if (init?.method === 'PUT') return putResponse ?? jsonResponse(prediction(JSON.parse(init.body as string)))
    if (init?.method === 'DELETE') return deleteResponse
    if (url === `/api/predictions/${detail.prediction_id}`) return jsonResponse(detail)
    if (url === `/api/predictions/${detail.prediction_id}/head-to-head`)
      return jsonResponse({ since: 0, matches: [] })
    return jsonResponse({ message: 'Prediction not found' }, false, 404)
  })
  globalThis.fetch = fetchMock as unknown as typeof fetch
  return fetchMock
}

const callsWith = (fetchMock: ReturnType<typeof mockBackend>, method: string) =>
  fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === method)

const renderDetail = async (id = 1) => {
  render(<PredictionDetail predictionId={id} />)
  await screen.findByRole('heading', { name: 'Team A vs Team B' })
}

describe('PredictionDetail', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    window.location.hash = '#predictions/1'
  })

  it('renders the saved comparison and insights tables, including an old snapshot missing fields', async () => {
    mockBackend()
    await renderDetail()
    const comparison = screen.getByRole('heading', { name: 'Team Comparison' }).nextElementSibling as HTMLElement
    expect(within(comparison).getByText('1500')).toBeInTheDocument()
    // Summary rows come from team 1's saved summary; team 2's old snapshot has none, so it shows "-"
    const pubWin = within(comparison).getByText('Pub Win %').closest('tr') as HTMLElement
    expect(pubWin).toHaveTextContent('56.0%')
    expect(pubWin).toHaveTextContent('-')

    const insights = screen.getByRole('heading', { name: 'Team Insights' }).nextElementSibling as HTMLElement
    expect(within(insights).getByText(/Core One/).closest('div')).toHaveTextContent('Core One · games: 10 · rank: 45')
  })

  it('shows the saved decision with the bookmaker values in their own box', async () => {
    mockBackend()
    await renderDetail()
    const bookmaker = screen.getByRole('group', { name: 'From bookmaker' })
    expect(bookmaker).toHaveTextContent('Coefficient Team A1.85')
    expect(bookmaker).toHaveTextContent('Coefficient Team B2.05')
    expect(bookmaker).toHaveTextContent('Seriesbo3')
    const decision = screen.getByRole('group', { name: 'My decision' })
    expect(decision).toHaveTextContent('Bet onTeam A')
    expect(decision).toHaveTextContent('Stake100')
    expect(decision).toHaveTextContent('CommentTeam A looks stronger')
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('shows the played heroes section disabled', async () => {
    mockBackend()
    await renderDetail()
    expect(screen.getByRole('group', { name: 'Played heroes' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Add played heroes' })).toBeDisabled()
  })

  it('hides the review until Add review is clicked, then offers the results of the format', async () => {
    mockBackend()
    await renderDetail()
    expect(screen.queryByRole('group', { name: 'Review' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Add review' }))
    const result = within(screen.getByRole('group', { name: 'Result' }))
    expect(result.getAllByRole('button').map((b) => b.textContent)).toEqual(['2-0', '2-1', '1-2', '0-2'])
    expect(screen.getByRole('button', { name: 'Save review' })).toBeDisabled()
  })

  it('sends the review and then shows the result and Edit review', async () => {
    const fetchMock = mockBackend()
    await renderDetail()
    await userEvent.click(screen.getByRole('button', { name: 'Add review' }))
    await userEvent.click(screen.getByRole('button', { name: '2-1' }))
    await userEvent.type(screen.getByRole('textbox', { name: 'Review note' }), 'Read it right')
    await userEvent.click(screen.getByRole('button', { name: 'Save review' }))

    await screen.findByRole('button', { name: 'Edit review' })
    const [[url, init]] = callsWith(fetchMock, 'PATCH')
    expect(url).toBe('/api/predictions/1')
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      team1_maps_won: 2,
      team2_maps_won: 1,
      review_note: 'Read it right',
    })
    const review = screen.getByRole('group', { name: 'Review' })
    expect(review).toHaveTextContent('ResultTeam A 2-1 Team B')
    expect(review).toHaveTextContent('OutcomeWon +85')
    expect(review).toHaveTextContent('Review noteRead it right')
  })

  it('opens Edit review with the saved result selected', async () => {
    mockBackend(predictionDetail({ team1_maps_won: 0, team2_maps_won: 2, review_note: 'Wrong', bet_won: false }))
    await renderDetail()
    expect(screen.getByRole('group', { name: 'Review' })).toHaveTextContent('OutcomeLost -100')
    await userEvent.click(screen.getByRole('button', { name: 'Edit review' }))
    expect(screen.getByRole('button', { name: '0-2' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('textbox', { name: 'Review note' })).toHaveValue('Wrong')
  })

  it('asks for maps won by each team when the format is unknown', async () => {
    const fetchMock = mockBackend(predictionDetail({ best_of: null }))
    await renderDetail()
    await userEvent.click(screen.getByRole('button', { name: 'Add review' }))
    await userEvent.type(screen.getByRole('textbox', { name: 'Maps won by Team A' }), '1')
    await userEvent.type(screen.getByRole('textbox', { name: 'Maps won by Team B' }), '0')
    await userEvent.click(screen.getByRole('button', { name: 'Save review' }))
    await screen.findByRole('button', { name: 'Edit review' })
    expect(JSON.parse((callsWith(fetchMock, 'PATCH')[0][1] as RequestInit).body as string)).toMatchObject({
      team1_maps_won: 1,
      team2_maps_won: 0,
    })
  })

  it('shows the backend error when the review is rejected', async () => {
    mockBackend(predictionDetail(), jsonResponse({ message: '2-0 is not accepted' }, false))
    await renderDetail()
    await userEvent.click(screen.getByRole('button', { name: 'Add review' }))
    await userEvent.click(screen.getByRole('button', { name: '2-0' }))
    await userEvent.click(screen.getByRole('button', { name: 'Save review' }))
    expect(await screen.findByText('2-0 is not accepted')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save review' })).toBeInTheDocument()
  })

  it('opens Edit with the saved values and hides the other actions', async () => {
    mockBackend()
    await renderDetail()
    await userEvent.click(screen.getByRole('button', { name: 'Edit' }))
    expect(screen.getByRole('textbox', { name: 'Coefficient Team A' })).toHaveValue('1.85')
    expect(screen.getByRole('textbox', { name: 'Coefficient Team B' })).toHaveValue('2.05')
    expect(screen.getByRole('combobox', { name: 'Series' })).toHaveValue('3')
    expect(screen.getByRole('radio', { name: 'Team A' })).toBeChecked()
    expect(screen.getByRole('textbox', { name: 'Stake' })).toHaveValue('100')
    expect(screen.getByRole('textbox', { name: 'Comment' })).toHaveValue('Team A looks stronger')
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add review' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.getByRole('group', { name: 'My decision' })).toHaveTextContent('Bet onTeam A')
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('sends the edited prediction and shows the new values', async () => {
    const fetchMock = mockBackend()
    await renderDetail()
    await userEvent.click(screen.getByRole('button', { name: 'Edit' }))
    const team1Odds = screen.getByRole('textbox', { name: 'Coefficient Team A' })
    await userEvent.clear(team1Odds)
    await userEvent.type(team1Odds, '1,9')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Series' }), 'n/a')
    await userEvent.click(screen.getByRole('radio', { name: 'Team B' }))
    const comment = screen.getByRole('textbox', { name: 'Comment' })
    await userEvent.clear(comment)
    await userEvent.type(comment, 'Changed my mind')
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await screen.findByRole('button', { name: 'Edit' })
    const [[url, init]] = callsWith(fetchMock, 'PUT')
    expect(url).toBe('/api/predictions/1')
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      team1_odds: 1.9,
      team2_odds: 2.05,
      best_of: null,
      bet_team: 2,
      stake: 100,
      comment: 'Changed my mind',
    })
    expect(screen.getByRole('group', { name: 'From bookmaker' })).toHaveTextContent('Coefficient Team A1.9')
    expect(screen.getByRole('group', { name: 'From bookmaker' })).toHaveTextContent('Seriesn/a')
    const decision = screen.getByRole('group', { name: 'My decision' })
    expect(decision).toHaveTextContent('Bet onTeam B')
    expect(decision).toHaveTextContent('CommentChanged my mind')
    // The saved snapshots stay on the page
    expect(screen.getByRole('heading', { name: 'Team Comparison' })).toBeInTheDocument()
  })

  it('sends no stake when the bet is removed', async () => {
    const fetchMock = mockBackend()
    await renderDetail()
    await userEvent.click(screen.getByRole('button', { name: 'Edit' }))
    await userEvent.click(screen.getByRole('radio', { name: 'No bet' }))
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await screen.findByRole('button', { name: 'Edit' })
    expect(JSON.parse((callsWith(fetchMock, 'PUT')[0][1] as RequestInit).body as string)).toMatchObject({
      bet_team: null,
      stake: null,
    })
  })

  it('blocks saving invalid odds and shows the backend error', async () => {
    const fetchMock = mockBackend(
      predictionDetail(),
      undefined,
      undefined,
      jsonResponse({ message: 'Saved result does not fit bo5' }, false),
    )
    await renderDetail()
    await userEvent.click(screen.getByRole('button', { name: 'Edit' }))
    const team1Odds = screen.getByRole('textbox', { name: 'Coefficient Team A' })
    await userEvent.clear(team1Odds)
    await userEvent.type(team1Odds, '1')
    expect(screen.getByText('Must be a number above 1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()

    await userEvent.type(team1Odds, '.5')
    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText('Saved result does not fit bo5')).toBeInTheDocument()
    expect(callsWith(fetchMock, 'PUT')).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeInTheDocument()
  })

  it('deletes the prediction after confirmation and goes back to the list', async () => {
    const fetchMock = mockBackend()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    await renderDetail()
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(window.location.hash).toBe('#predictions'))
    expect(callsWith(fetchMock, 'DELETE')[0][0]).toBe('/api/predictions/1')
  })

  it('does not delete when the confirmation is cancelled', async () => {
    const fetchMock = mockBackend()
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    await renderDetail()
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(callsWith(fetchMock, 'DELETE')).toHaveLength(0)
  })

  it('shows not found with a link back to the list', async () => {
    mockBackend()
    render(<PredictionDetail predictionId={99} />)
    expect(await screen.findByText('Prediction not found')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '← All predictions' })).toHaveAttribute('href', '#predictions')
  })
})

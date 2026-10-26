import { useEffect, useState } from 'react'
import { formatShortDateTime } from '../format'
import { betTotals, isSettled, outcome, requestJson, teamLabel } from '../predictions'
import type { Prediction } from '../types'
import { bestOfLabel, scoreLabel, usePage } from '../series'
import { Pager, TeamCells } from './seriesTable'
import BetOutcome, { Loss, Profit, SIMULATION_NOTE } from './BetOutcome'

type Filter = 'all' | 'pending' | 'settled'

const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'pending', label: 'Pending' },
  { id: 'settled', label: 'Settled' },
]

const betText = (p: Prediction): string => {
  if (p.bet_team === null) return 'No bet'
  const team = teamLabel(p.bet_team === 1 ? p.team1 : p.team2, p.bet_team - 1)
  return p.stake !== null ? `${team} · ${p.stake}` : team
}

/** Predictions, laid out like the Finished Matches table (time, Bo, teams, score), then odds, bet and outcome. */
function PredictionTable({ predictions }: { predictions: Prediction[] }) {
  const { page, pages, shown, setPage } = usePage(predictions)

  return (
    <>
      <table className="stats-table matches-table prediction-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Best of</th>
            <th colSpan={2}>Team #1</th>
            <th colSpan={2}>Team #2</th>
            <th>Score</th>
            <th>Odds</th>
            <th>Bet</th>
            <th>Outcome</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((p) => {
            const result = outcome(p)
            return (
              <tr
                key={p.prediction_id}
                className="prediction-row-link"
                onClick={() => (window.location.hash = `#predictions/${p.prediction_id}`)}
              >
                <td>
                  <a href={`#predictions/${p.prediction_id}`}>{formatShortDateTime(p.created_at)}</a>
                </td>
                <td>{bestOfLabel(p.best_of)}</td>
                <TeamCells name={teamLabel(p.team1, 0)} logoUrl={p.team1.logo_url} />
                <TeamCells name={teamLabel(p.team2, 1)} logoUrl={p.team2.logo_url} />
                <td>{scoreLabel(p.team1_maps_won, p.team2_maps_won)}</td>
                <td>
                  {p.team1_odds} / {p.team2_odds}
                </td>
                <td>{betText(p)}</td>
                <td className={`outcome outcome-${result}`}>
                  <BetOutcome prediction={p} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <Pager page={page} pages={pages} setPage={setPage} />
    </>
  )
}

/** Predictions tab: every saved prediction, newest first, with a pending/settled filter and totals. */
function PredictionList() {
  const [predictions, setPredictions] = useState<Prediction[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>('all')

  useEffect(() => {
    let cancelled = false
    requestJson<Prediction[]>('/api/predictions')
      .then((data) => !cancelled && setPredictions(data))
      .catch((err: Error) => !cancelled && setError(err.message))
    return () => {
      cancelled = true
    }
  }, [])

  if (error) return <div className="error-message">Failed to load predictions: {error}</div>
  if (!predictions) return <p>Loading predictions...</p>

  const filtered = predictions.filter((p) => filter === 'all' || (filter === 'settled') === isSettled(p))
  const outcomes = filtered.map(outcome)
  const count = (o: string) => outcomes.filter((x) => x === o).length
  const totals = betTotals(filtered)

  return (
    <section className="prediction-list">
      <div className="prediction-list-toolbar">
        <div className="filter-buttons" role="group" aria-label="Filter">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              className={`secondary-btn ${filter === f.id ? 'active' : ''}`}
              aria-pressed={filter === f.id}
              onClick={() => setFilter(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>
        <p className="prediction-totals">
          Bets: {filtered.length - count('no_bet')} · Won: {count('won')} · Lost: {count('lost')} · Pending:{' '}
          {count('pending')} · Possible profit: <Profit value={totals.profit} /> · Possible loss:{' '}
          <Loss value={totals.loss} /> <span className="simulation-badge">{SIMULATION_NOTE}</span>
        </p>
      </div>

      {filtered.length === 0 ? (
        <p>{predictions.length ? 'No predictions match this filter.' : 'No predictions yet. Log one on the Compare tab.'}</p>
      ) : (
        <PredictionTable key={filter} predictions={filtered} />
      )}
    </section>
  )
}

export default PredictionList

import { useEffect, useState } from 'react'
import { formatDateTime } from '../format'
import { OUTCOME_LABELS, isSettled, outcome, requestJson, resultText, seriesLabel, teamLabel } from '../predictions'
import type { Prediction } from '../types'

type Filter = 'all' | 'pending' | 'settled'

const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'pending', label: 'Pending' },
  { id: 'settled', label: 'Settled' },
]

const TeamCell = ({ team, index }: { team: Prediction['team1']; index: number }) => (
  <span className="prediction-team">
    {team.logo_url && <img src={team.logo_url} alt="" className="prediction-team-logo" />}
    {teamLabel(team, index)}
  </span>
)

const betText = (p: Prediction): string => {
  if (p.bet_team === null) return 'No bet'
  const team = teamLabel(p.bet_team === 1 ? p.team1 : p.team2, p.bet_team - 1)
  return p.stake !== null ? `${team} · ${p.stake}` : team
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

  const shown = predictions.filter((p) => filter === 'all' || (filter === 'settled') === isSettled(p))
  const outcomes = shown.map(outcome)
  const count = (o: string) => outcomes.filter((x) => x === o).length

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
          Bets: {shown.length - count('no_bet')} · Won: {count('won')} · Lost: {count('lost')} · Pending:{' '}
          {count('pending')}
        </p>
      </div>

      {shown.length === 0 ? (
        <p>{predictions.length ? 'No predictions match this filter.' : 'No predictions yet. Log one on the Compare tab.'}</p>
      ) : (
        <table className="stats-table prediction-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Teams</th>
              <th>Odds</th>
              <th>Series</th>
              <th>Bet</th>
              <th>Result</th>
              <th>Outcome</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((p, i) => (
              <tr
                key={p.prediction_id}
                className="prediction-row-link"
                onClick={() => (window.location.hash = `#predictions/${p.prediction_id}`)}
              >
                <td>{formatDateTime(p.created_at)}</td>
                <td>
                  <a href={`#predictions/${p.prediction_id}`} className="prediction-teams">
                    <TeamCell team={p.team1} index={0} />
                    <span className="versus">vs</span>
                    <TeamCell team={p.team2} index={1} />
                  </a>
                </td>
                <td>
                  {p.team1_odds} / {p.team2_odds}
                </td>
                <td>{seriesLabel(p.best_of)}</td>
                <td>{betText(p)}</td>
                <td>{resultText(p)}</td>
                <td className={`outcome outcome-${outcomes[i]}`}>{OUTCOME_LABELS[outcomes[i]]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

export default PredictionList

import { useEffect, useState } from 'react'
import { formatDateTime } from '../format'
import {
  type BetChoice,
  SERIES_OPTIONS,
  decisionBody,
  decisionErrors,
  isSettled,
  outcome,
  requestJson,
  resultOptions,
  seriesLabel,
  teamLabel,
} from '../predictions'
import type { Prediction, PredictionDetail as Detail, Snapshot, TeamData } from '../types'
import ComparisonTable from './ComparisonTable'
import BetOutcome from './BetOutcome'
import HeadToHeadTable from './HeadToHeadTable'
import InsightsTable, { type PlayerRanks } from './InsightsTable'

interface PredictionDetailProps {
  predictionId: number
}

// The team as saved; old snapshots may lack fields the tables expect, so the lists default to empty
const snapshotTeam = (snapshot: Snapshot): TeamData =>
  ({ players: [], other_players: [], ...snapshot.data.team }) as TeamData

const snapshotRanks = (snapshot: Snapshot): PlayerRanks =>
  new Map((snapshot.data.players ?? []).map((p) => [p.account_id, p.rank]))

/** Review form: the final score (buttons valid for the format, or two numbers when it is unknown) and a note. */
function ReviewForm({
  prediction,
  onSaved,
  onCancel,
}: {
  prediction: Prediction
  onSaved: (updated: Prediction) => void
  onCancel: () => void
}) {
  const names = [teamLabel(prediction.team1, 0), teamLabel(prediction.team2, 1)]
  const options = resultOptions(prediction.best_of)
  const [score, setScore] = useState<[string, string]>([
    prediction.team1_maps_won?.toString() ?? '',
    prediction.team2_maps_won?.toString() ?? '',
  ])
  const [note, setNote] = useState(prediction.review_note ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const complete = score.every((s) => /^\d+$/.test(s.trim()))

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      const updated = await requestJson<Prediction>(`/api/predictions/${prediction.prediction_id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ team1_maps_won: Number(score[0]), team2_maps_won: Number(score[1]), review_note: note }),
      })
      onSaved(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setSaving(false)
    }
  }

  return (
    <fieldset className="decision-box review-form" disabled={saving}>
      <legend>Review</legend>
      <div className="prediction-field">
        <span>
          Result ({names[0]} - {names[1]})
        </span>
        {options.length ? (
          <div className="filter-buttons" role="group" aria-label="Result">
            {options.map(([a, b]) => {
              const selected = score[0] === String(a) && score[1] === String(b)
              return (
                <button
                  key={`${a}-${b}`}
                  type="button"
                  className={`secondary-btn ${selected ? 'active' : ''}`}
                  aria-pressed={selected}
                  onClick={() => setScore([String(a), String(b)])}
                >
                  {a}-{b}
                </button>
              )
            })}
          </div>
        ) : (
          <div className="prediction-row">
            {names.map((name, i) => (
              <label key={i} className="prediction-field">
                <span>Maps won by {name}</span>
                <input
                  type="text"
                  inputMode="numeric"
                  value={score[i]}
                  onChange={(e) => setScore(i === 0 ? [e.target.value, score[1]] : [score[0], e.target.value])}
                />
              </label>
            ))}
          </div>
        )}
      </div>
      <label className="prediction-field">
        <span>Review note</span>
        <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      {error && <div className="error-message">{error}</div>}
      <div className="prediction-actions">
        <button type="button" className="secondary-btn" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="check-btn" onClick={save} disabled={!complete}>
          {saving ? 'Saving...' : 'Save review'}
        </button>
      </div>
    </fieldset>
  )
}

/** Edit form for the bookmaker values and the decision, filled with the saved values. Snapshots stay as saved. */
function DecisionForm({
  prediction,
  onSaved,
  onCancel,
}: {
  prediction: Prediction
  onSaved: (updated: Prediction) => void
  onCancel: () => void
}) {
  const names = [teamLabel(prediction.team1, 0), teamLabel(prediction.team2, 1)]
  const [odds, setOdds] = useState([String(prediction.team1_odds), String(prediction.team2_odds)])
  const [bestOf, setBestOf] = useState(prediction.best_of?.toString() ?? '')
  const [bet, setBet] = useState<BetChoice>(prediction.bet_team ? (String(prediction.bet_team) as BetChoice) : 'none')
  const [stake, setStake] = useState(prediction.stake?.toString() ?? '')
  const [comment, setComment] = useState(prediction.comment)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { oddsErrors, stakeError, invalid } = decisionErrors(odds, bet, stake)
  const fieldError = (message: string | null) => (message ? <span className="field-error">{message}</span> : null)

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      const updated = await requestJson<Prediction>(`/api/predictions/${prediction.prediction_id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(decisionBody(odds, bestOf, bet, stake, comment)),
      })
      onSaved(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setSaving(false)
    }
  }

  return (
    <fieldset className="prediction-fieldset" disabled={saving}>
      <fieldset className="bookmaker-box">
        <legend>From bookmaker</legend>
        <div className="prediction-row">
          {names.map((name, i) => (
            <label key={i} className="prediction-field">
              <span>Coefficient {name}</span>
              <input
                type="text"
                inputMode="decimal"
                value={odds[i]}
                onChange={(e) => setOdds(odds.map((v, j) => (j === i ? e.target.value : v)))}
              />
              {fieldError(oddsErrors[i])}
            </label>
          ))}
          <label className="prediction-field">
            <span>Series</span>
            <select value={bestOf} onChange={(e) => setBestOf(e.target.value)}>
              {SERIES_OPTIONS.map((o) => (
                <option key={o.label} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </fieldset>

      <fieldset className="decision-box">
        <legend>My decision</legend>
        <div className="prediction-row">
          <div className="prediction-field" role="radiogroup" aria-label="Bet on">
            <span>Bet on</span>
            <div className="bet-options">
              {(['1', '2', 'none'] as const).map((choice) => (
                <label key={choice}>
                  <input
                    type="radio"
                    name="edit-bet-team"
                    value={choice}
                    checked={bet === choice}
                    onChange={() => setBet(choice)}
                  />
                  {choice === 'none' ? 'No bet' : names[Number(choice) - 1]}
                </label>
              ))}
            </div>
          </div>
          <label className="prediction-field">
            <span>Stake</span>
            <input
              type="text"
              inputMode="decimal"
              value={stake}
              disabled={bet === 'none'}
              onChange={(e) => setStake(e.target.value)}
            />
            {fieldError(stakeError)}
          </label>
        </div>
        <label className="prediction-field">
          <span>Comment</span>
          <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
        </label>
      </fieldset>

      {error && <div className="error-message">{error}</div>}
      <div className="prediction-actions">
        <button type="button" className="secondary-btn" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="check-btn" onClick={save} disabled={invalid}>
          {saving ? 'Saving...' : 'Save changes'}
        </button>
      </div>
    </fieldset>
  )
}

/**
 * One prediction: the Team Comparison and Team Insights tables as saved in its snapshots, the head-to-head matches,
 * the decision (editable with "Edit"), the review (hidden until "Add review"), a delete button and the played heroes
 * placeholder.
 */
function PredictionDetail({ predictionId }: PredictionDetailProps) {
  const [detail, setDetail] = useState<Detail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reviewing, setReviewing] = useState(false)
  const [editing, setEditing] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    requestJson<Detail>(`/api/predictions/${predictionId}`)
      .then((data) => !cancelled && setDetail(data))
      .catch((err: Error) => !cancelled && setError(err.message))
    return () => {
      cancelled = true
    }
  }, [predictionId])

  const back = (
    <a href="#predictions" className="back-link">
      ← All predictions
    </a>
  )

  if (error)
    return (
      <section className="prediction-detail">
        {back}
        <div className="error-message">{error}</div>
      </section>
    )
  if (!detail) return <p>Loading prediction...</p>

  const snapshots = [detail.team1_snapshot, detail.team2_snapshot]
  const teams = snapshots.map(snapshotTeam)
  const summaries = snapshots.map((s) => s.data.summary ?? null)
  const names = [teamLabel(detail.team1, 0), teamLabel(detail.team2, 1)]
  const settled = isSettled(detail)
  const result = outcome(detail)

  const handleDelete = async () => {
    if (!window.confirm(`Delete prediction #${detail.prediction_id}? Its snapshots stay.`)) return
    try {
      await requestJson(`/api/predictions/${detail.prediction_id}`, { method: 'DELETE' })
      window.location.hash = '#predictions'
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : 'An error occurred')
    }
  }

  return (
    <section className="prediction-detail">
      {back}
      <h2>
        {names[0]} vs {names[1]}
      </h2>
      <p className="prediction-hint">
        Prediction #{detail.prediction_id}, saved {formatDateTime(detail.created_at)}. Snapshots taken{' '}
        {snapshots.map((s) => formatDateTime(s.taken_at)).join(' and ')}, {snapshots[0].days}-day window.
      </p>

      <div className="results-columns">
        <div className="results-column">
          <h2>Team Comparison</h2>
          <ComparisonTable
            teams={teams}
            summaries={summaries}
            showSummaryRows={summaries.some(Boolean)}
            days={snapshots[0].days}
          />
        </div>
        <div className="results-column">
          <h2>Team Insights</h2>
          <InsightsTable teams={teams} ranks={snapshots.map(snapshotRanks)} />
        </div>
      </div>

      <h2>Head-to-head</h2>
      <HeadToHeadTable predictionId={detail.prediction_id} predictedAt={detail.created_at} teamNames={names} />

      <div className="prediction-panel">
        <h2>Prediction</h2>
        <div className="prediction-fieldset">
          {editing ? (
            <DecisionForm
              prediction={detail}
              onCancel={() => setEditing(false)}
              onSaved={(updated) => {
                setDetail({ ...detail, ...updated })
                setEditing(false)
              }}
            />
          ) : (
            <>
              <fieldset className="bookmaker-box">
                <legend>From bookmaker</legend>
                <dl className="prediction-values">
                  <div>
                    <dt>Coefficient {names[0]}</dt>
                    <dd>{detail.team1_odds}</dd>
                  </div>
                  <div>
                    <dt>Coefficient {names[1]}</dt>
                    <dd>{detail.team2_odds}</dd>
                  </div>
                  <div>
                    <dt>Series</dt>
                    <dd>{seriesLabel(detail.best_of)}</dd>
                  </div>
                </dl>
              </fieldset>

              <fieldset className="decision-box">
                <legend>My decision</legend>
                <dl className="prediction-values">
                  <div>
                    <dt>Bet on</dt>
                    <dd>{detail.bet_team ? names[detail.bet_team - 1] : 'No bet'}</dd>
                  </div>
                  {detail.bet_team !== null && (
                    <div>
                      <dt>Stake</dt>
                      <dd>{detail.stake ?? '-'}</dd>
                    </div>
                  )}
                </dl>
                <dl className="prediction-values">
                  <div>
                    <dt>Comment</dt>
                    <dd className="prediction-comment">{detail.comment || '-'}</dd>
                  </div>
                </dl>
              </fieldset>
            </>
          )}

          {settled && !reviewing && (
            <fieldset className="decision-box">
              <legend>Review</legend>
              <dl className="prediction-values">
                <div>
                  <dt>Result</dt>
                  <dd>
                    {names[0]} {detail.team1_maps_won}-{detail.team2_maps_won} {names[1]}
                  </dd>
                </div>
                <div>
                  <dt>Outcome</dt>
                  <dd className={`outcome outcome-${result}`}>
                    <BetOutcome prediction={detail} />
                  </dd>
                </div>
              </dl>
              {detail.review_note && (
                <dl className="prediction-values">
                  <div>
                    <dt>Review note</dt>
                    <dd className="prediction-comment">{detail.review_note}</dd>
                  </div>
                </dl>
              )}
            </fieldset>
          )}

          {reviewing ? (
            <ReviewForm
              prediction={detail}
              onCancel={() => setReviewing(false)}
              onSaved={(updated) => {
                setDetail({ ...detail, ...updated })
                setReviewing(false)
              }}
            />
          ) : (
            !editing && (
              <div className="prediction-actions">
                <button type="button" className="secondary-btn" onClick={handleDelete}>
                  Delete
                </button>
                <button type="button" className="secondary-btn" onClick={() => setEditing(true)}>
                  Edit
                </button>
                <button type="button" className="check-btn" onClick={() => setReviewing(true)}>
                  {settled ? 'Edit review' : 'Add review'}
                </button>
              </div>
            )
          )}
          {deleteError && <div className="error-message">{deleteError}</div>}

          <fieldset className="decision-box heroes-placeholder" disabled>
            <legend>Played heroes</legend>
            <p className="prediction-hint">Coming soon.</p>
            <div>
              <button type="button" className="secondary-btn">
                Add played heroes
              </button>
            </div>
          </fieldset>
        </div>
      </div>
    </section>
  )
}

export default PredictionDetail

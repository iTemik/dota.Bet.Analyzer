import { useState } from 'react'
import { teamName } from '../format'
import { type BetChoice, SERIES_OPTIONS, decisionBody, decisionErrors } from '../predictions'
import type { StatisticsResult, TeamData } from '../types'

interface PredictionPanelProps {
  teams: (TeamData | undefined)[] // team 1 and team 2
  results: (StatisticsResult | undefined)[] // GET /api/results/{task_id} per team
  days: number // statistics window the teams were loaded with
}

type SaveResult = { kind: 'prediction'; id: number } | { kind: 'snapshots'; ids: number[] }

// Body of POST /api/snapshots: the team as shown (task_id dropped), its summary and the players' ranks
const snapshotBody = (team: TeamData, result: StatisticsResult | undefined, days: number) => {
  const shown: Partial<TeamData> = { ...team }
  delete shown.task_id
  return {
    team_id: team.team_id,
    days,
    team: shown,
    summary: result?.summary ?? null,
    players: (result?.results ?? [])
      .filter((r) => !r.error)
      .map((r) => ({ account_id: r.account_id, rank: r.rank ?? null, match_count: r.match_count ?? null })),
  }
}

// POST a JSON body; returns the response JSON or throws with the backend's message
const postJson = async (url: string, body: unknown) => {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new Error(data?.message || `HTTP error! status: ${response.status}`)
  return data
}

/**
 * "Log prediction" panel under the comparison tables. Bookmaker values (odds, series) are in their own box,
 * apart from the decision (bet, stake, comment). Saving stores both team snapshots, then the prediction.
 */
function PredictionPanel({ teams, results, days }: PredictionPanelProps) {
  const [odds, setOdds] = useState(['', ''])
  const [bestOf, setBestOf] = useState('3')
  const [bet, setBet] = useState<BetChoice>('none')
  const [stake, setStake] = useState('')
  const [comment, setComment] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<SaveResult | null>(null)

  const ready = teams.every(Boolean) && results.every((r) => r?.summary)
  const names = teams.map(teamName)

  // Any change makes the form a new prediction again
  const edit = <T,>(setter: (value: T) => void) => (value: T) => {
    setter(value)
    setSaved(null)
  }

  const { oddsErrors, stakeError, invalid } = decisionErrors(odds, bet, stake)

  const saveSnapshots = async (): Promise<number[]> => {
    const snapshots = await Promise.all(
      teams.map((team, i) => postJson('/api/snapshots', snapshotBody(team as TeamData, results[i], days))),
    )
    return snapshots.map((s) => s.snapshot_id)
  }

  const run = async (action: () => Promise<SaveResult>) => {
    setSaving(true)
    setError(null)
    try {
      setSaved(await action())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
    } finally {
      setSaving(false)
    }
  }

  const handleSavePrediction = () => {
    setSubmitted(true)
    if (invalid) return
    run(async () => {
      const [team1SnapshotId, team2SnapshotId] = await saveSnapshots()
      const prediction = await postJson('/api/predictions', {
        team1_snapshot_id: team1SnapshotId,
        team2_snapshot_id: team2SnapshotId,
        ...decisionBody(odds, bestOf, bet, stake, comment),
      })
      return { kind: 'prediction', id: prediction.prediction_id }
    })
  }

  const handleSaveSnapshots = () => run(async () => ({ kind: 'snapshots', ids: await saveSnapshots() }))

  const fieldError = (message: string | null) =>
    submitted && message ? <span className="field-error">{message}</span> : null

  return (
    <section className="prediction-panel" aria-labelledby="prediction-panel-title">
      <h2 id="prediction-panel-title">Log prediction</h2>
      {!ready && <p className="prediction-hint">Available once the player statistics of both teams have loaded.</p>}

      <fieldset disabled={!ready || saving} className="prediction-fieldset">
        <fieldset className="bookmaker-box">
          <legend>From bookmaker</legend>
          <div className="prediction-row">
            {names.map((name, i) => (
              <label key={i} className="prediction-field">
                <span>Coefficient {name}</span>
                <input
                  type="text"
                  inputMode="decimal"
                  placeholder="1.85"
                  value={odds[i]}
                  onChange={(e) => edit(setOdds)(odds.map((v, j) => (j === i ? e.target.value : v)))}
                />
                {fieldError(oddsErrors[i])}
              </label>
            ))}
            <label className="prediction-field">
              <span>Series</span>
              <select value={bestOf} onChange={(e) => edit(setBestOf)(e.target.value)}>
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
                      name="bet-team"
                      value={choice}
                      checked={bet === choice}
                      onChange={() => edit(setBet)(choice)}
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
                onChange={(e) => edit(setStake)(e.target.value)}
              />
              {fieldError(stakeError)}
            </label>
          </div>
          <label className="prediction-field">
            <span>Comment</span>
            <textarea rows={3} value={comment} onChange={(e) => edit(setComment)(e.target.value)} />
          </label>
        </fieldset>

        <div className="prediction-actions">
          <button type="button" className="secondary-btn" onClick={handleSaveSnapshots}>
            Save snapshots only
          </button>
          <button
            type="button"
            className="check-btn"
            onClick={handleSavePrediction}
            disabled={saved?.kind === 'prediction'}
          >
            {saving ? 'Saving...' : 'Save prediction'}
          </button>
        </div>
      </fieldset>

      {error && <div className="error-message">{error}</div>}
      {saved?.kind === 'prediction' && (
        <p className="prediction-saved">
          Prediction saved: <a href={`#predictions/${saved.id}`}>#{saved.id}</a>
        </p>
      )}
      {saved?.kind === 'snapshots' && (
        <p className="prediction-saved">Snapshots saved: {saved.ids.map((id) => `#${id}`).join(', ')}</p>
      )}
    </section>
  )
}

export default PredictionPanel

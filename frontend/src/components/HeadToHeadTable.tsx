import { useEffect, useState } from 'react'
import { formatDateTime } from '../format'
import { requestJson } from '../predictions'
import type { HeadToHead } from '../types'

interface HeadToHeadTableProps {
  predictionId: number
  teamNames: string[]
}

/** League matches between the prediction's two teams, newest first; matches before the prediction are tagged. */
function HeadToHeadTable({ predictionId, teamNames }: HeadToHeadTableProps) {
  const [data, setData] = useState<HeadToHead | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    requestJson<HeadToHead>(`/api/predictions/${predictionId}/head-to-head`)
      .then((result) => !cancelled && setData(result))
      .catch((err: Error) => !cancelled && setError(err.message))
    return () => {
      cancelled = true
    }
  }, [predictionId])

  if (error) return <div className="error-message">{error}</div>
  if (!data) return <p>Loading head-to-head matches...</p>
  if (!data.matches.length)
    return <p className="prediction-hint">No matches between these teams since {formatDateTime(data.since)}.</p>

  return (
    <table className="stats-table head-to-head-table">
      <thead>
        <tr>
          <th>Match ID</th>
          <th>Date</th>
          <th>Result</th>
        </tr>
      </thead>
      <tbody>
        {data.matches.map((m) => (
          <tr key={m.match_id} className={m.before_prediction ? 'before-prediction' : undefined}>
            <td>
              <a href={`https://www.opendota.com/matches/${m.match_id}`} target="_blank" rel="noreferrer">
                {m.match_id}
              </a>
            </td>
            <td>
              {formatDateTime(m.start_time)}
              {m.before_prediction && <span className="before-prediction-tag">before prediction</span>}
            </td>
            <td>{m.team1_won === null ? 'unknown' : `${teamNames[m.team1_won ? 0 : 1]} won`}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default HeadToHeadTable

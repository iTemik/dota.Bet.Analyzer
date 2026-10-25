import { useEffect, useState } from 'react'
import { formatDateTime } from '../format'
import { requestJson } from '../predictions'
import type { Match, MatchTeam, Matches } from '../types'

interface MatchesTablesProps {
  // Called with an upcoming series the user clicked
  onSelect: (match: Match) => void
}

// A series with a team still to be decided can't be checked
const isCheckable = (match: Match): boolean => match.team1.name !== 'TBD' && match.team2.name !== 'TBD'

const bestOf = (match: Match): string => (match.best_of ? `Bo${match.best_of}` : '-')

const score = (match: Match): string =>
  match.score1 === null || match.score1 === undefined || match.score2 === null || match.score2 === undefined
    ? '-'
    : `${match.score1}:${match.score2}`

function TeamCells({ team }: { team: MatchTeam }) {
  return (
    <>
      <td>{team.name}</td>
      <td className="match-team-icon">{team.logo_url && <img src={team.logo_url} alt={`${team.name} logo`} />}</td>
    </>
  )
}

function MatchesTable({ matches, finished, onSelect }: { matches: Match[]; finished: boolean; onSelect?: (match: Match) => void }) {
  return (
    <table className="stats-table matches-table">
      <thead>
        <tr>
          <th>Time</th>
          <th>Best of</th>
          <th colSpan={2}>Team #1</th>
          <th colSpan={2}>Team #2</th>
          {finished && <th>Score</th>}
        </tr>
      </thead>
      <tbody>
        {matches.map((m, i) => {
          const select = onSelect && isCheckable(m) ? () => onSelect(m) : undefined
          return (
            <tr
              key={`${i}-${m.start_time}-${m.team1.name}-${m.team2.name}`}
              className={select ? 'match-row-clickable' : undefined}
              onClick={select}
              title={select ? 'Check statistics of these teams' : undefined}
            >
              <td>{formatDateTime(m.start_time)}</td>
              <td>{bestOf(m)}</td>
              <TeamCells team={m.team1} />
              <TeamCells team={m.team2} />
              {finished && <td>{score(m)}</td>}
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

/** Upcoming (soonest first) and recently finished (newest first) series from Liquipedia. */
function MatchesTables({ onSelect }: MatchesTablesProps) {
  const [data, setData] = useState<Matches | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    requestJson<Matches>('/api/matches')
      .then((result) => !cancelled && setData(result))
      .catch((err: Error) => !cancelled && setError(err.message))
    return () => {
      cancelled = true
    }
  }, [])

  if (error) return <div className="error-message">Matches: {error}</div>
  if (!data) return <p>Loading matches...</p>
  const upcoming = data.upcoming ?? []
  const finished = data.finished ?? []

  return (
    <div className="matches-section">
      <h2>Upcoming Matches</h2>
      {upcoming.length ? (
        <MatchesTable matches={upcoming} finished={false} onSelect={onSelect} />
      ) : (
        <p className="prediction-hint">No upcoming matches.</p>
      )}
      <h2>Finished Matches</h2>
      {finished.length ? (
        <MatchesTable matches={finished} finished />
      ) : (
        <p className="prediction-hint">No finished matches.</p>
      )}
    </div>
  )
}

export default MatchesTables

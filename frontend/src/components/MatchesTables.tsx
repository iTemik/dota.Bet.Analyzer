import { useEffect, useState } from 'react'
import { formatShortDateTime } from '../format'
import { requestJson } from '../predictions'
import type { Match, Matches, MatchTournament } from '../types'
import { bestOfLabel, scoreLabel, usePage } from '../series'
import { Pager, TeamCells } from './seriesTable'

interface MatchesTablesProps {
  // Called with an upcoming series the user clicked
  onSelect: (match: Match) => void
}

// A series with a team still to be decided can't be checked
const isCheckable = (match: Match): boolean => match.team1.name !== 'TBD' && match.team2.name !== 'TBD'

/** Two cells for the tournament: icon, then the name linked to its Liquipedia page. */
function TournamentCells({ tournament }: { tournament: MatchTournament | null }) {
  return (
    <>
      <td className="match-team-icon">
        {tournament?.icon && <img src={tournament.icon} alt={`${tournament.name} icon`} />}
      </td>
      <td>
        {tournament?.url ? (
          // A click on the link opens Liquipedia, not the statistics of the row
          <a href={tournament.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
            {tournament.name}
          </a>
        ) : (
          (tournament?.name ?? '-')
        )}
      </td>
    </>
  )
}

interface MatchesTableProps {
  label: string
  matches: Match[]
  finished: boolean
  onSelect?: (match: Match) => void
}

/** One table of series, PAGE_SIZE rows per page with Previous / Next buttons when there is more than one page. */
function MatchesTable({ label, matches, finished, onSelect }: MatchesTableProps) {
  const { page, pages, shown, setPage } = usePage(matches)

  return (
    <>
      <table className="stats-table matches-table" aria-label={label}>
        <thead>
          <tr>
            <th>Time</th>
            <th colSpan={2}>Tournament</th>
            <th>Best of</th>
            <th colSpan={2}>Team #1</th>
            <th colSpan={2}>Team #2</th>
            {finished && <th>Score</th>}
          </tr>
        </thead>
        <tbody>
          {shown.map((m, i) => {
            const select = onSelect && isCheckable(m) ? () => onSelect(m) : undefined
            return (
              <tr
                key={`${page}-${i}-${m.start_time}-${m.team1.name}-${m.team2.name}`}
                className={select ? 'match-row-clickable' : undefined}
                onClick={select}
                title={select ? 'Check statistics of these teams' : undefined}
              >
                <td>{formatShortDateTime(m.start_time)}</td>
                <TournamentCells tournament={m.tournament} />
                <td>{bestOfLabel(m.best_of)}</td>
                <TeamCells name={m.team1.name} logoUrl={m.team1.logo_url} />
                <TeamCells name={m.team2.name} logoUrl={m.team2.logo_url} />
                {finished && <td>{scoreLabel(m.score1, m.score2)}</td>}
              </tr>
            )
          })}
        </tbody>
      </table>
      <Pager page={page} pages={pages} setPage={setPage} />
    </>
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
        <MatchesTable label="Upcoming matches" matches={upcoming} finished={false} onSelect={onSelect} />
      ) : (
        <p className="prediction-hint">No upcoming matches.</p>
      )}
      <h2>Finished Matches</h2>
      {finished.length ? (
        <MatchesTable label="Finished matches" matches={finished} finished />
      ) : (
        <p className="prediction-hint">No finished matches.</p>
      )}
      {/* Liquipedia content is CC-BY-SA 3.0, which requires naming it as the source */}
      <p className="prediction-hint">
        Match data:{' '}
        <a href="https://liquipedia.net/dota2/Liquipedia:Matches" target="_blank" rel="noreferrer">
          Liquipedia
        </a>{' '}
        (CC-BY-SA 3.0)
      </p>
    </div>
  )
}

export default MatchesTables

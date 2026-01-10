import { useState } from 'react'
import './App.css'

// Color constants - defined in App.css as CSS variables
const COLOR_POSITIVE = '#6b9d7a'
const COLOR_NEGATIVE = '#9d6b6b'

// TODO: actualize to the Stats structure of the backend
interface TeamData {
  error_code: null | string
  error_message: null | string
  rating: null | number
  delta: number
  logo_url?: string
  other_players: unknown[]
  players: unknown[]
  tag: string
  team: string
  team_id: number
}

interface Statistics {
  teams: TeamData[]
}

function App() {
  const [team1, setTeam1] = useState('')
  const [team2, setTeam2] = useState('')
  const [statistics, setStatistics] = useState<Statistics | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleCheck = async () => {
    if (!team1.trim() || !team2.trim()) {
      setError('Please enter both team names')
      return
    }

    setLoading(true)
    setError(null)

    try {
      const params = new URLSearchParams()
      params.append('team', team1)
      params.append('team', team2)

      const response = await fetch(`/statistics?${params.toString()}`)

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const data = await response.json()
      setStatistics(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
      setStatistics(null)
    } finally {
      setLoading(false)
    }
  }

  const getDeltaBackgroundColor = (delta: number | undefined): string => {
    if (!delta) return 'transparent'
    if (delta < -15) return COLOR_NEGATIVE
    if (delta > 15) return COLOR_POSITIVE
    return 'transparent'
  }

  const getRatingBackgroundColors = (
    rating1: number | null | undefined,
    rating2: number | null | undefined
  ): [string, string] => {
    if (!rating1 || !rating2) return ['transparent', 'transparent']
    const diff = Math.abs(rating1 - rating2)
    if (diff <= 100) return ['transparent', 'transparent']

    if (rating1 > rating2) {
      return [COLOR_POSITIVE, COLOR_NEGATIVE]
    } else {
      return [COLOR_NEGATIVE, COLOR_POSITIVE]
    }
  }

  return (
    <div className="container">
      <h1>Dota 2 Bet Analyzer</h1>

      <div className="form-section">
        <div className="input-groups-row">
          <div className="input-group">
            <label htmlFor="team1">Team #1</label>
            <input
              id="team1"
              type="text"
              value={team1}
              onChange={(e) => setTeam1(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCheck()}
              placeholder="Enter first team name"
              autoFocus
            />
          </div>

          <div className="input-group">
            <label htmlFor="team2">Team #2</label>
            <input
              id="team2"
              type="text"
              value={team2}
              onChange={(e) => setTeam2(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCheck()}
              placeholder="Enter second team name"
            />
          </div>
        </div>

        <button onClick={handleCheck} disabled={loading} className="check-btn">
          {loading ? 'Loading...' : 'Check Statistics'}
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}

      {statistics && (
        <div className="results-section">
          <h2>Team Comparison</h2>
          <table className="stats-table">
            <thead>
              <tr>
                <th></th>
                <th>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.5rem' }}>
                    <span>{statistics.teams?.[0]?.team ? statistics.teams[0].team : 'Team #1'}</span>
                    {statistics.teams?.[0]?.logo_url && (
                      <img src={statistics.teams[0].logo_url} alt="Team 1 Logo" style={{ height: '80px', width: '100px', objectFit: 'contain' }} />
                    )}
                  </div>
                </th>
                <th>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.5rem' }}>
                    <span>{statistics.teams?.[1]?.team ? statistics.teams[1].team : 'Team #2'}</span>
                    {statistics.teams?.[1]?.logo_url && (
                      <img src={statistics.teams[1].logo_url} alt="Team 2 Logo" style={{ height: '80px', width: '100px', objectFit: 'contain' }} />
                    )}
                  </div>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="row-label">Team Tag</td>
                <td>{statistics.teams?.[0]?.tag ? statistics.teams[0].tag : '-'}</td>
                <td>{statistics.teams?.[1]?.tag ? statistics.teams[1].tag : '-'}</td>
              </tr>
              <tr>
                <td className="row-label">Team ID</td>
                <td>{statistics.teams?.[0]?.team_id ? statistics.teams[0].team_id : '-'}</td>
                <td>{statistics.teams?.[1]?.team_id ? statistics.teams[1].team_id : '-'}</td>
              </tr>
              <tr>
                <td className="row-label">Rating</td>
                <td style={{ backgroundColor: getRatingBackgroundColors(statistics.teams?.[0]?.rating, statistics.teams?.[1]?.rating)[0] }}>
                  {statistics.teams?.[0]?.rating ? statistics.teams[0].rating : '-'}
                </td>
                <td style={{ backgroundColor: getRatingBackgroundColors(statistics.teams?.[0]?.rating, statistics.teams?.[1]?.rating)[1] }}>
                  {statistics.teams?.[1]?.rating ? statistics.teams[1].rating : '-'}
                </td>
              </tr>
              <tr>
                <td className="row-label">Last match rating</td>
                <td style={{ backgroundColor: getDeltaBackgroundColor(statistics.teams?.[0]?.delta) }}>
                  {statistics.teams?.[0]?.delta ? statistics.teams[0].delta.toFixed(1) : '-'}
                </td>
                <td style={{ backgroundColor: getDeltaBackgroundColor(statistics.teams?.[1]?.delta) }}>
                  {statistics.teams?.[1]?.delta ? statistics.teams[1].delta.toFixed(1) : '-'}
                </td>
              </tr>
            </tbody>
          </table>

          <h2>Raw JSON</h2>
          <pre>{JSON.stringify(statistics, null, 2)}</pre>
        </div>
      )}
    </div>
  )
}

export default App

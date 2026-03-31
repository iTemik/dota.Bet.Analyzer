import { useEffect, useRef, useState } from 'react'
import './App.css'
import TeamAutocomplete from './components/TeamAutocomplete'
import { VERSION } from './version'

// Color constants - defined in App.css as CSS variables
const COLOR_POSITIVE = '#6b9d7a'
const COLOR_NEGATIVE = '#9d6b6b'

interface Player {
  name: string
  id: number
}

interface TeamData {
  error_code: null | string
  rating: null | number
  delta: number
  logo_url?: string
  task_id?: string | null
  other_players: Player[]
  players: Player[]
  tag: string
  team: string
  team_id: number
}

interface Statistics {
  teams: TeamData[]
}

interface ProgressData {
  step: number
  message: string
  progress: number
  data: unknown
  timestamp: number
}

/**
 * Team roster (account lists) is collected indirectly:
 *    - Frontend calls: GET /api/statistics?team=Alliance&team=OG
 *    - Backend fetches team data from OpenDota API (compute_statistics() -> _create_team_stats() -> get_players_by_team())
 *    - Player accounts are extracted from team roster in database
 *    - This is a background task (players_statistics_task).
 *    - It's needed to poll progress /api/stream-progress/{task_id} and get results at /api/results/{task_id}
 */
function App() {
  const [team1, setTeam1] = useState('')
  const [team2, setTeam2] = useState('')
  const [team1Id, setTeam1Id] = useState<number | null>(null)
  const [team2Id, setTeam2Id] = useState<number | null>(null)
  const [team1SelectedName, setTeam1SelectedName] = useState<string>('')
  const [team2SelectedName, setTeam2SelectedName] = useState<string>('')
  const [statistics, setStatistics] = useState<Statistics | null>(null)
  const [summaryData, setSummaryData] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [progress, setProgress] = useState<ProgressData | null>(null)
  const [backendVersion, setBackendVersion] = useState<string | null>(null)
  const [showRawStats, setShowRawStats] = useState(false)
  const [showSummaryData, setShowSummaryData] = useState(false)
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const currentSearchIdRef = useRef<number>(0)

  useEffect(() => {
    const fetchBackendVersion = async () => {
      try {
        const response = await fetch('/api/version')
        const text = await response.text()
        //console.log('Raw response text:', JSON.stringify(text))
        if (response.ok) {
          const data = JSON.parse(text)
          //console.log('Parsed backend version response:', data)
          setBackendVersion(data.backend || data.backend_version || 'unknown')
        } else {
          console.error('Backend version response not ok:', response.status)
        }
      } catch (err) {
        console.error('Failed to fetch backend version:', err)
      }
    }

    fetchBackendVersion()
  }, [])

  const handleCheck = async () => {
    if (!team1.trim() || !team2.trim()) {
      setError('Please enter both team names')
      return
    }

    // Increment search ID to mark this as a new search
    currentSearchIdRef.current += 1
    const thisSearchId = currentSearchIdRef.current

    // Stop any existing polling
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current)
      pollIntervalRef.current = null
    }

    setLoading(true)
    setError(null)
    setStatistics(null)
    setSummaryData(null)
    setProgress(null)

    try {
      const params = new URLSearchParams()

      // For team1: Only send team_id if the user selected from the list (name matches selected name)
      if (team1Id !== null && team1 === team1SelectedName) {
        params.append('team_id', String(team1Id))
      } else {
        params.append('team', team1)
      }

      // For team2: Only send team_id if the user selected from the list (name matches selected name)
      if (team2Id !== null && team2 === team2SelectedName) {
        params.append('team_id', String(team2Id))
      } else {
        params.append('team', team2)
      }

      const response = await fetch(`/api/statistics?${params.toString()}`)

      if (!response.ok) {
        // Try to extract error message from response body
        try {
          const errorData = await response.json()
          const errorMsg = errorData.message || `HTTP error! status: ${response.status}`
          throw new Error(errorMsg)
        } catch {
          throw new Error(`HTTP error! status: ${response.status}`)
        }
      }

      const data = await response.json()

      // Reset summary data when new statistics are loaded
      // This ensures old data doesn't persist between searches
      setSummaryData(null)
      setStatistics(data)

      // Check if any team has a task_id (ongoing background task)
      const taskIds = data.teams
        .filter((team: TeamData) => team.task_id)
        .map((team: TeamData) => team.task_id)

      if (taskIds.length > 0) {
        // Poll progress for all tasks
        await pollTasksProgress(taskIds, thisSearchId)
      } else {
        setLoading(false)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
      setStatistics(null)
      setSummaryData(null)
      setLoading(false)
    }
  }

  const pollTasksProgress = async (taskIds: (string | undefined)[], searchId: number) => {
    const MAX_POLLING_TIME = 5 * 60 * 1000 // 5 minutes in milliseconds
    const POLL_INTERVAL = 3 * 1000 // 3 seconds in milliseconds
    const startTime = Date.now()

    pollIntervalRef.current = setInterval(async () => {
      try {
        // Skip processing if a new search has started
        if (currentSearchIdRef.current !== searchId) {
          if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current)
            pollIntervalRef.current = null
          }
          return
        }

        const elapsedTime = Date.now() - startTime

        // Check if polling timeout exceeded
        if (elapsedTime > MAX_POLLING_TIME) {
          setError('Polling timeout: Task took longer than 5 minutes')
          setLoading(false)
          if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current)
            pollIntervalRef.current = null
          }
          return
        }

        let allCompleted = true
        const summaries: Record<string, unknown> = {}

        for (const taskId of taskIds) {
          if (!taskId) continue

          const progressUrl = `/api/stream-progress/${taskId}`
          const progressResponse = await fetch(progressUrl)
          if (!progressResponse.ok) {
            setError(`Failed to fetch progress for task ${taskId}: HTTP ${progressResponse.status}`)
            setLoading(false)
            if (pollIntervalRef.current) {
              clearInterval(pollIntervalRef.current)
              pollIntervalRef.current = null
            }
            return
          }

          // Read response text once
          let responseText: string
          try {
            responseText = await progressResponse.text()
          } catch (textError) {
            setError(`Failed to read response for task ${taskId}: ${textError}`)
            setLoading(false)
            if (pollIntervalRef.current) {
              clearInterval(pollIntervalRef.current)
              pollIntervalRef.current = null
            }
            return
          }

          // Parse NDJSON format (newline-delimited JSON)
          let progressData: ProgressData
          try {
            // Split by newlines and filter out empty lines
            const lines = responseText.split('\n').filter(line => line.trim())

            if (lines.length === 0) {
              setError(`No data found in response for task ${taskId}`)
              setLoading(false)
              if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current)
                pollIntervalRef.current = null
              }
              return
            }

            // Try to parse each line until we find valid JSON
            // Use the last valid JSON line as the most recent progress
            let lastValidJson: ProgressData | null = null
            const allLines: unknown[] = []

            for (const line of lines) {
              try {
                const parsedLine = JSON.parse(line)
                lastValidJson = parsedLine as ProgressData
                allLines.push(parsedLine)
              } catch (e) {
                // Skip lines that aren't valid JSON
                continue
              }
            }

            if (!lastValidJson) {
              setError(`No valid JSON found in response for task ${taskId}`)
              setLoading(false)
              if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current)
                pollIntervalRef.current = null
              }
              return
            }

            progressData = lastValidJson
          } catch (parseError) {
            setError(`Error parsing response for task ${taskId}: ${parseError}`)
            setLoading(false)
            if (pollIntervalRef.current) {
              clearInterval(pollIntervalRef.current)
              pollIntervalRef.current = null
            }
            return
          }

          setProgress(progressData)

          // Check if task is complete (progress === 100)
          if (progressData.progress === 100) {
            summaries[taskId] = progressData.data
          } else if (progressData.progress < 100) {
            allCompleted = false
          }
        }

        // If all tasks are complete, fetch detailed results
        if (allCompleted && Object.keys(summaries).length > 0) {
          setLoading(false)
          if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current)
            pollIntervalRef.current = null
          }

          // Fetch detailed results for each completed task
          try {
            const detailedResults: Record<string, unknown> = {}

            for (const taskId of taskIds) {
              if (!taskId) continue

              const resultsResponse = await fetch(`/api/results/${taskId}`)
              if (resultsResponse.ok) {
                const resultsData = await resultsResponse.json()
                detailedResults[taskId] = resultsData
              } else {
                console.warn(`Failed to fetch results for task ${taskId}: HTTP ${resultsResponse.status}`)
                detailedResults[taskId] = summaries[taskId]
              }
            }

            setSummaryData(detailedResults)
          } catch (err) {
            console.error('Error fetching detailed results:', err)
            // Fall back to summary data if results fetch fails
            setSummaryData(summaries)
          }
        }
      } catch (err) {
        console.error('Error polling progress:', err)
        setError(`Polling error: ${err instanceof Error ? err.message : String(err)}`)
        setLoading(false)
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current)
          pollIntervalRef.current = null
        }
      }
    }, POLL_INTERVAL)
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
    if (!rating1 || !rating2) {
      return ['transparent', 'transparent']
    }
    const diff = Math.abs(rating1 - rating2)
    if (diff <= 100) {
      return ['transparent', 'transparent']
    }

    if (rating1 > rating2) {
      return [COLOR_POSITIVE, COLOR_NEGATIVE]
    } else {
      return [COLOR_NEGATIVE, COLOR_POSITIVE]
    }
  }

  const getSummaryValueColors = (value1: unknown, value2: unknown): [string, string] => {
    const num1 = typeof value1 === 'number' ? value1 : null
    const num2 = typeof value2 === 'number' ? value2 : null

    if (num1 === null || num2 === null) {
      return ['transparent', 'transparent']
    }
    if (num1 === num2) {
      return ['transparent', 'transparent']
    }

    if (num1 > num2) {
      return [COLOR_POSITIVE, COLOR_NEGATIVE]
    } else {
      return [COLOR_NEGATIVE, COLOR_POSITIVE]
    }
  }

  const getInverseSummaryValueColors = (value1: unknown, value2: unknown): [string, string] => {
    const num1 = typeof value1 === 'number' ? value1 : null
    const num2 = typeof value2 === 'number' ? value2 : null

    if (num1 === null || num2 === null) {
      return ['transparent', 'transparent']
    }
    if (num1 === num2) {
      return ['transparent', 'transparent']
    }

    // Inverse logic: lower values are positive, higher values are negative
    if (num1 < num2) {
      return [COLOR_POSITIVE, COLOR_NEGATIVE]
    } else {
      return [COLOR_NEGATIVE, COLOR_POSITIVE]
    }
  }

  const getSummaryForTeam = (taskId: string | null | undefined) => {
    if (!taskId || !summaryData) {
      return null
    }

    const data = summaryData[taskId]
    if (!data) {
      console.warn(`No summary data found for taskId: ${taskId}, available keys: ${Object.keys(summaryData).join(', ')}`)
      return null
    }

    // Handle different possible data structures
    if (typeof data === 'object') {
      // If it's wrapped in a 'summary' key, unwrap it (this is the expected structure)
      const obj = data as Record<string, unknown>
      if (obj.summary && typeof obj.summary === 'object') {
        const summary = obj.summary as Record<string, unknown>
        return summary
      }
      if (obj.data && typeof obj.data === 'object') {
        return obj.data as Record<string, unknown>
      }
      // Otherwise assume it's the summary object directly
      return obj as Record<string, unknown>
    }

    return null
  }

  return (
    <div className="container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', gap: '1rem' }}>
        <h1>Dota 2 Bet Analyzer</h1>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.25rem' }}>
          <span style={{ color: '#666', fontSize: '0.85rem', fontWeight: '500' }}>Frontend: v{VERSION}</span>
          <span style={{ color: '#999', fontSize: '0.8rem' }}>Backend: v {backendVersion || 'loading...'}</span>
        </div>
      </div>

      <div className="form-section">
        <div className="input-groups-row">
          <div className="input-group">
            <label htmlFor="team1">Team #1</label>
            <TeamAutocomplete
              value={team1}
              onChange={(value) => {
                setTeam1(value)
                // Mark that no explicit selection is active
                // onSelect will set the selectedName if user picks from list
                setTeam1SelectedName('')
              }}
              onSelect={(team) => {
                setTeam1Id(team.team_id)
                setTeam1SelectedName(team.name)
              }}
              placeholder="Enter first team name"
              autoFocus
            />
          </div>

          <div className="input-group">
            <label htmlFor="team2">Team #2</label>
            <TeamAutocomplete
              value={team2}
              onChange={(value) => {
                setTeam2(value)
                // Mark that no explicit selection is active
                // onSelect will set the selectedName if user picks from list
                setTeam2SelectedName('')
              }}
              onSelect={(team) => {
                setTeam2Id(team.team_id)
                setTeam2SelectedName(team.name)
              }}
              placeholder="Enter second team name"
            />
          </div>
        </div>

        <button onClick={handleCheck} disabled={loading} className="check-btn">
          {loading ? 'Loading...' : 'Check Statistics'}
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}

      {progress && loading && (
        <div className="progress-section">
          <h2>Task Progress</h2>
          <p>{progress.message}</p>
          <div style={{ width: '100%', height: '20px', backgroundColor: '#e0e0e0', borderRadius: '4px', overflow: 'hidden' }}>
            <div
              style={{
                width: `${progress.progress}%`,
                height: '100%',
                backgroundColor: '#6b9d7a',
                transition: 'width 0.3s ease',
              }}
            />
          </div>
          <p>{progress.progress}% complete</p>
        </div>
      )}

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
              {summaryData && (() => {
                const team0Summary = getSummaryForTeam(statistics.teams?.[0]?.task_id)
                const team1Summary = getSummaryForTeam(statistics.teams?.[1]?.task_id)
                return (
                  <>
                    <tr>
                      <td className="row-label">Rating Matches</td>
                      <td style={{ backgroundColor: getSummaryValueColors(team0Summary?.rating_matches, team1Summary?.rating_matches)[0] }}>
                        {String(team0Summary?.rating_matches ?? '-')}
                      </td>
                      <td style={{ backgroundColor: getSummaryValueColors(team0Summary?.rating_matches, team1Summary?.rating_matches)[1] }}>
                        {String(team1Summary?.rating_matches ?? '-')}
                      </td>
                    </tr>
                    <tr>
                      <td className="row-label">Tournament Matches</td>
                      <td style={{ backgroundColor: getSummaryValueColors(team0Summary?.tournament_matches, team1Summary?.tournament_matches)[0] }}>
                        {String(team0Summary?.tournament_matches ?? '-')}
                      </td>
                      <td style={{ backgroundColor: getSummaryValueColors(team0Summary?.tournament_matches, team1Summary?.tournament_matches)[1] }}>
                        {String(team1Summary?.tournament_matches ?? '-')}
                      </td>
                    </tr>
                    <tr>
                      <td className="row-label">Win Percentage</td>
                      <td style={{ backgroundColor: getSummaryValueColors(team0Summary?.win_percentage, team1Summary?.win_percentage)[0] }}>
                        {team0Summary?.win_percentage ? (team0Summary.win_percentage as number).toFixed(1) + '%' : '-'}
                      </td>
                      <td style={{ backgroundColor: getSummaryValueColors(team0Summary?.win_percentage, team1Summary?.win_percentage)[1] }}>
                        {team1Summary?.win_percentage ? (team1Summary.win_percentage as number).toFixed(1) + '%' : '-'}
                      </td>
                    </tr>
                    <tr>
                      <td className="row-label">Average Player Rank</td>
                      <td style={{ backgroundColor: getInverseSummaryValueColors(team0Summary?.avg_rank, team1Summary?.avg_rank)[0] }}>
                        {team0Summary?.avg_rank ? (team0Summary.avg_rank as number).toFixed(0) : '-'}
                      </td>
                      <td style={{ backgroundColor: getInverseSummaryValueColors(team0Summary?.avg_rank, team1Summary?.avg_rank)[1] }}>
                        {team1Summary?.avg_rank ? (team1Summary.avg_rank as number).toFixed(0) : '-'}
                      </td>
                    </tr>
                    <tr>
                      <td className="row-label">Bad Rank Players</td>
                      <td style={{ backgroundColor: getInverseSummaryValueColors(team0Summary?.bad_rank_players, team1Summary?.bad_rank_players)[0] }}>
                        {String(team0Summary?.bad_rank_players ?? '-')}
                      </td>
                      <td style={{ backgroundColor: getInverseSummaryValueColors(team0Summary?.bad_rank_players, team1Summary?.bad_rank_players)[1] }}>
                        {String(team1Summary?.bad_rank_players ?? '-')}
                      </td>
                    </tr>
                    <tr>
                      <td className="row-label">Other Matches</td>
                      <td>{String(team0Summary?.other_matches ?? '-')}</td>
                      <td>{String(team1Summary?.other_matches ?? '-')}</td>
                    </tr>
                    <tr>
                      <td className="row-label">Average Matches Per Player</td>
                      <td style={{ backgroundColor: getSummaryValueColors(team0Summary?.matches_avg, team1Summary?.matches_avg)[0] }}>
                        {team0Summary?.matches_avg ? (team0Summary.matches_avg as number).toFixed(2) : '-'}
                      </td>
                      <td style={{ backgroundColor: getSummaryValueColors(team0Summary?.matches_avg, team1Summary?.matches_avg)[1] }}>
                        {team1Summary?.matches_avg ? (team1Summary.matches_avg as number).toFixed(2) : '-'}
                      </td>
                    </tr>
                    <tr>
                      <td className="row-label">Median Matches Per Player</td>
                      <td style={{ backgroundColor: getSummaryValueColors(team0Summary?.matches_median, team1Summary?.matches_median)[0] }}>
                        {team0Summary?.matches_median ? (team0Summary.matches_median as number).toFixed(2) : '-'}
                      </td>
                      <td style={{ backgroundColor: getSummaryValueColors(team0Summary?.matches_median, team1Summary?.matches_median)[1] }}>
                        {team1Summary?.matches_median ? (team1Summary.matches_median as number).toFixed(2) : '-'}
                      </td>
                    </tr>
                  </>
                )
              })()}
            </tbody>
          </table>

          <div className="collapsible-header" onClick={() => setShowRawStats(!showRawStats)}>
            <h2>Raw team stats JSON</h2>
            <span className={`collapsible-toggle ${showRawStats ? 'expanded' : ''}`}>▼</span>
          </div>
          <div className={`collapsible-content ${showRawStats ? 'expanded' : ''}`}>
            <pre>{JSON.stringify(statistics, null, 2)}</pre>
          </div>

          {summaryData && (
            <>
              <div className="collapsible-header" onClick={() => setShowSummaryData(!showSummaryData)}>
                <h2>Match Statistics Summary</h2>
                <span className={`collapsible-toggle ${showSummaryData ? 'expanded' : ''}`}>▼</span>
              </div>
              <div className={`collapsible-content ${showSummaryData ? 'expanded' : ''}`}>
                <pre>{JSON.stringify(summaryData, null, 2)}</pre>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

export default App

import { type ReactNode, useEffect, useRef, useState } from 'react'
import './App.css'
import TeamAutocomplete from './components/TeamAutocomplete'
import { type ProgressData, parseProgress } from './progress'
import { VERSION } from './version'

// Color constants - defined in App.css as CSS variables
const COLOR_POSITIVE = '#6b9d7a'
const COLOR_NEGATIVE = '#9d6b6b'
// Roster and match history window, sent to /api/statistics as `days` (same default as the backend)
const STATS_DAYS = 20

type Summary = Record<string, unknown> | null

// Team Comparison row: `compare` picks the number to colour by, `better` says which side wins
interface CompareRowConfig {
  label: ReactNode
  title?: string
  summary?: boolean // shown only once the match summary has arrived
  compare?: (team: TeamData | undefined, summary: Summary) => number | null
  better?: 'higher' | 'lower'
  threshold?: number // differences up to this are not coloured
  color?: (team: TeamData | undefined) => string // per-team colour, for rows that don't compare
  render: (team: TeamData | undefined, summary: Summary) => ReactNode
}

const asNumber = (value: unknown): number | null => (typeof value === 'number' ? value : null)

// Colours for team 1 and team 2: the better value is positive, the other negative
const compareColors = (a: number | null, b: number | null, better: 'higher' | 'lower', threshold = 0): [string, string] => {
  if (a === null || b === null || Math.abs(a - b) <= threshold) return ['transparent', 'transparent']
  const firstWins = better === 'higher' ? a > b : a < b
  return firstWins ? [COLOR_POSITIVE, COLOR_NEGATIVE] : [COLOR_NEGATIVE, COLOR_POSITIVE]
}

const CompareRow = ({ row, teams, summaries }: { row: CompareRowConfig; teams: (TeamData | undefined)[]; summaries: Summary[] }) => {
  let colors: string[] | null = null
  if (row.compare && row.better) {
    colors = compareColors(row.compare(teams[0], summaries[0]), row.compare(teams[1], summaries[1]), row.better, row.threshold)
  } else if (row.color) {
    colors = teams.map(row.color)
  }
  return (
    <tr>
      <td className="row-label" title={row.title}>
        {row.label}
      </td>
      {teams.map((team, i) => (
        <td key={i} style={colors ? { backgroundColor: colors[i] } : undefined}>
          {row.render(team, summaries[i])}
        </td>
      ))}
    </tr>
  )
}

interface Player {
  name: string
  id: number
  games?: number | null
  is_core?: boolean | null
}

interface LeagueForm {
  days: number
  matches: number
  wins: number
  losses: number
  win_percentage: number | null
  last_match_time: number | null
}

interface TeamData {
  error_code: null | string
  rating: null | number
  delta: number
  logo_url?: string
  task_id?: string | null
  other_players: Player[]
  players: Player[]
  roster_source?: 'recent_matches' | 'pro_players' | null
  roster_games?: number | null
  standins_count?: number
  roster_last_match_time?: number | null
  latest_match_time?: number | null
  latest_match_standins?: number | null
  roster_state?: 'stable' | 'new_players' | 'new_team' | null
  league_form?: LeagueForm | null
  tag: string
  team: string
  team_id: number
}

interface Statistics {
  teams: TeamData[]
}

/**
 * Team roster (account lists) is collected indirectly:
 *    - Frontend calls: GET /api/statistics?team=Alliance&team=OG
 *    - Backend fetches team data from OpenDota API (compute_statistics() -> _create_team_stats() -> resolve_roster())
 *    - Player accounts are the players with the most tournament games in the window (stale team list as fallback)
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
    // The backend may still be starting (it syncs pro players on startup), so retry for a while
    const VERSION_RETRIES = 15
    const VERSION_RETRY_DELAY = 2000
    let cancelled = false
    let retryTimer: ReturnType<typeof setTimeout> | null = null

    const fetchBackendVersion = async (attempt: number) => {
      try {
        const response = await fetch('/api/version')
        const text = await response.text()
        if (response.ok) {
          const data = JSON.parse(text)
          if (!cancelled) setBackendVersion(data.backend || data.backend_version || 'unknown')
          return
        }
        console.error('Backend version response not ok:', response.status)
      } catch (err) {
        console.error('Failed to fetch backend version:', err)
      }
      if (cancelled) return
      if (attempt < VERSION_RETRIES) {
        retryTimer = setTimeout(() => fetchBackendVersion(attempt + 1), VERSION_RETRY_DELAY)
      } else {
        setBackendVersion('unavailable')
      }
    }

    fetchBackendVersion(1)
    return () => {
      cancelled = true
      if (retryTimer) clearTimeout(retryTimer)
    }
  }, [])

  const stopPolling = () => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current)
      pollIntervalRef.current = null
    }
  }

  // Stop polling and show the error
  const failPolling = (message: string) => {
    setError(message)
    setLoading(false)
    stopPolling()
  }

  const handleCheck = async () => {
    if (!team1.trim() || !team2.trim()) {
      setError('Please enter both team names')
      return
    }

    // Increment search ID to mark this as a new search
    currentSearchIdRef.current += 1
    const thisSearchId = currentSearchIdRef.current

    stopPolling()

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

      params.append('days', String(STATS_DAYS))

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
          stopPolling()
          return
        }

        if (Date.now() - startTime > MAX_POLLING_TIME) {
          failPolling('Polling timeout: Task took longer than 5 minutes')
          return
        }

        let allCompleted = true
        const summaries: Record<string, unknown> = {}

        for (const taskId of taskIds) {
          if (!taskId) continue

          const progressResponse = await fetch(`/api/stream-progress/${taskId}`)
          if (!progressResponse.ok) {
            failPolling(`Failed to fetch progress for task ${taskId}: HTTP ${progressResponse.status}`)
            return
          }

          let responseText: string
          try {
            responseText = await progressResponse.text()
          } catch (textError) {
            failPolling(`Failed to read response for task ${taskId}: ${textError}`)
            return
          }

          const parsed = parseProgress(responseText)
          if (!parsed.ok) {
            failPolling(
              parsed.reason === 'empty'
                ? `No data found in response for task ${taskId}`
                : `No valid JSON found in response for task ${taskId}`
            )
            return
          }
          const progressData = parsed.progress

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
          stopPolling()

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
        failPolling(`Polling error: ${err instanceof Error ? err.message : String(err)}`)
      }
    }, POLL_INTERVAL)
  }

  const getDeltaBackgroundColor = (delta: number | undefined): string => {
    if (!delta) return 'transparent'
    if (delta < -15) return COLOR_NEGATIVE
    if (delta > 15) return COLOR_POSITIVE
    return 'transparent'
  }

  const formatDate = (unixTime: number | null | undefined): string => {
    if (!unixTime) return '-'
    return new Date(unixTime * 1000).toLocaleDateString()
  }

  // Roster state, from best to worst; stand-ins are players outside the core (below 75%, or 50%, of the games)
  const ROSTER_STATES: Record<string, { rank: number; label: string; hint: string }> = {
    stable: { rank: 0, label: 'Stable', hint: 'Only the core players played' },
    standins: { rank: 1, label: 'Stand-ins', hint: 'A clear core of 5 players, plus stand-ins in some games' },
    new_team: { rank: 2, label: 'New team', hint: 'No clear core of 5 players: players rotate' },
  }

  const getRosterRank = (team: TeamData | undefined): number | null =>
    team?.roster_source === 'recent_matches' && team.roster_state ? (ROSTER_STATES[team.roster_state]?.rank ?? null) : null

  const renderRosterState = (team: TeamData | undefined) => {
    const state = team?.roster_source === 'recent_matches' && team.roster_state ? ROSTER_STATES[team.roster_state] : null
    if (!team || !state) return '-'
    const standins = getStandins(team).length
    const suffix = standins ? ` (${standins} stand-in${standins === 1 ? '' : 's'})` : ''
    return <span title={state.hint}>{`${state.label}${suffix}`}</span>
  }

  // "(X of N)" next to a player who missed some of the team's tournament games in the window
  const formatGamesShare = (player: Player, team: TeamData): string => {
    const total = team.roster_games
    if (!player.games || !total || player.games >= total) return ''
    return ` (${player.games} of ${total})`
  }

  // Players without a name on OpenDota come as "#<account id>"; show them as an ID so they don't read as a nickname
  const renderName = (player: Player) => {
    const accountId = /^#(\d+)$/.exec(player.name)?.[1]
    if (!accountId) return player.name
    return (
      <span className="account-id" title="No player name on OpenDota; this is the account ID">
        ID {accountId}
      </span>
    )
  }

  // Core: players with 75% (or 50%) of the games; without a clear core, the main 5
  const hasCore = (team: TeamData) => team.players.some((p) => p.is_core)
  const getCorePlayers = (team: TeamData): Player[] =>
    team.roster_source === 'recent_matches' && hasCore(team) ? team.players.filter((p) => p.is_core) : team.players
  // Stand-ins: everyone else who played for the team in the window
  const getStandins = (team: TeamData): Player[] => {
    const core = new Set(getCorePlayers(team).map((p) => p.id))
    return [...team.players, ...(team.other_players ?? [])].filter((p) => !core.has(p.id) && p.games !== 0)
  }

  const renderCorePlayers = (team: TeamData | undefined) => {
    if (!team || !team.players?.length) return '-'
    const clearCore = team.roster_source === 'recent_matches' && hasCore(team)
    return (
      <div className="roster">
        {getCorePlayers(team).map((p) => (
          <div key={p.id}>
            {renderName(p)}
            {formatGamesShare(p, team)}
          </div>
        ))}
        {team.roster_source !== 'recent_matches' && <div className="roster-source">unconfirmed: no recent tournament match</div>}
        {team.roster_source === 'recent_matches' && !clearCore && <div className="roster-source">no clear core: players rotate</div>}
      </div>
    )
  }

  const renderPlayedList = (players: Player[], team: TeamData) => {
    if (!players.length) return 'None'
    return (
      <div className="roster">
        {players.map((p) => (
          <div key={p.id}>
            {renderName(p)}
            {formatGamesShare(p, team)}
          </div>
        ))}
      </div>
    )
  }

  const renderStandinPlayers = (team: TeamData | undefined) =>
    team?.roster_source === 'recent_matches' ? renderPlayedList(getStandins(team), team) : '-'

  // Other players: listed on the team by OpenDota but without league games in the window
  const renderOtherPlayers = (team: TeamData | undefined) => {
    if (!team) return '-'
    const others = team.other_players ?? []
    return renderPlayedList(team.roster_source === 'recent_matches' ? others.filter((p) => p.games === 0) : others, team)
  }

  // Team insights: one row per insight, Team #1 vs Team #2; add new insights to this list
  const insightRows: { label: string; render: (team: TeamData | undefined) => ReactNode }[] = [
    { label: 'Core Players', render: renderCorePlayers },
    { label: 'Stand-ins', render: renderStandinPlayers },
    { label: 'Other Players', render: renderOtherPlayers },
    {
      label: 'Last Tournament Match',
      render: (team) => {
        if (team?.roster_source !== 'recent_matches' || !team.latest_match_time) return '-'
        // Mention players outside the core only when there were any
        const outside = team.latest_match_standins ?? 0
        const suffix = outside ? `, ${outside} player${outside === 1 ? '' : 's'} outside the core` : ''
        return `${formatDate(team.latest_match_time)}${suffix}`
      },
    },
  ]

  const formatLeagueRecord = (form: LeagueForm | null | undefined): string => {
    if (!form || !form.matches) return '-'
    return `${form.wins}-${form.losses} (${(form.win_percentage ?? 0).toFixed(1)}%)`
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

  const formatPercent = (value: unknown): string => (typeof value === 'number' ? value.toFixed(1) + '%' : '-')
  const formatFixed = (value: unknown, digits: number): string => (value ? (value as number).toFixed(digits) : '-')

  const teams = [statistics?.teams?.[0], statistics?.teams?.[1]]
  const summaries = teams.map((team) => getSummaryForTeam(team?.task_id))

  // Team Comparison: one row per stat, Team #1 vs Team #2; add new stats to this list
  const compareRows: CompareRowConfig[] = [
    { label: 'Team Tag', render: (team) => (team?.tag ? team.tag : '-') },
    { label: 'Team ID', render: (team) => (team?.team_id ? team.team_id : '-') },
    {
      label: 'Rating',
      compare: (team) => team?.rating || null,
      better: 'higher',
      threshold: 100,
      render: (team) => (team?.rating ? team.rating : '-'),
    },
    {
      label: 'Last match rating',
      color: (team) => getDeltaBackgroundColor(team?.delta),
      render: (team) => (team?.delta ? team.delta.toFixed(1) : '-'),
    },
    { label: 'Roster Changes', compare: getRosterRank, better: 'lower', render: renderRosterState },
    {
      label: `Tournaments Record (${teams[0]?.league_form?.days ?? STATS_DAYS}d)`,
      compare: (team) => asNumber(team?.league_form?.win_percentage),
      better: 'higher',
      render: (team) => formatLeagueRecord(team?.league_form),
    },
    {
      label: 'Last Match',
      title: 'Latest tournament game played by at least 3 of the 5 players',
      render: (team) => formatDate(team?.roster_last_match_time ?? team?.league_form?.last_match_time),
    },
    {
      label: 'Rating Matches',
      summary: true,
      compare: (_, s) => asNumber(s?.rating_matches),
      better: 'higher',
      render: (_, s) => String(s?.rating_matches ?? '-'),
    },
    {
      label: (
        <>
          Lobby Matches
          <br />
          (tournaments + scrims)
        </>
      ),
      summary: true,
      compare: (_, s) => asNumber(s?.tournament_matches),
      better: 'higher',
      render: (_, s) => String(s?.tournament_matches ?? '-'),
    },
    {
      label: 'Pub Win %',
      summary: true,
      compare: (_, s) => asNumber(s?.rating_win_percentage),
      better: 'higher',
      render: (_, s) => formatPercent(s?.rating_win_percentage),
    },
    {
      label: 'Lobby Win %',
      summary: true,
      compare: (_, s) => asNumber(s?.tournament_win_percentage),
      better: 'higher',
      render: (_, s) => formatPercent(s?.tournament_win_percentage),
    },
    {
      label: 'Average Player Rank',
      summary: true,
      compare: (_, s) => asNumber(s?.avg_rank),
      better: 'lower',
      render: (_, s) => formatFixed(s?.avg_rank, 0),
    },
    {
      label: (
        <>
          Low Rank Players
          <br />
          (тысячники в команде)
        </>
      ),
      summary: true,
      compare: (_, s) => asNumber(s?.bad_rank_players),
      better: 'lower',
      render: (_, s) => String(s?.bad_rank_players ?? '-'),
    },
    { label: 'Other Matches', summary: true, render: (_, s) => String(s?.other_matches ?? '-') },
    {
      label: 'Average Matches Per Player',
      summary: true,
      compare: (_, s) => asNumber(s?.matches_avg),
      better: 'higher',
      render: (_, s) => formatFixed(s?.matches_avg, 2),
    },
    {
      label: 'Median Matches Per Player',
      summary: true,
      compare: (_, s) => asNumber(s?.matches_median),
      better: 'higher',
      render: (_, s) => formatFixed(s?.matches_median, 2),
    },
  ]

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
          <div className="results-columns">
            <div className="results-column">
              <h2>Team Comparison</h2>
              <table className="stats-table comparison-table">
                <thead>
                  <tr>
                    <th></th>
                    <th>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.5rem' }}>
                        <span>{teams[0]?.team ? teams[0].team : 'Team #1'}</span>
                        {teams[0]?.logo_url && (
                          <img src={teams[0].logo_url} alt="Team 1 Logo" style={{ height: '80px', width: '100px', objectFit: 'contain' }} />
                        )}
                      </div>
                    </th>
                    <th>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.5rem' }}>
                        <span>{teams[1]?.team ? teams[1].team : 'Team #2'}</span>
                        {teams[1]?.logo_url && (
                          <img src={teams[1].logo_url} alt="Team 2 Logo" style={{ height: '80px', width: '100px', objectFit: 'contain' }} />
                        )}
                      </div>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {compareRows
                    .filter((row) => !row.summary || summaryData)
                    .map((row, i) => (
                      <CompareRow key={i} row={row} teams={teams} summaries={summaries} />
                    ))}
                </tbody>
              </table>
            </div>

            <div className="results-column">
              <h2>Team Insights</h2>
              <table className="stats-table insights-table">
                <thead>
                  <tr>
                    <th></th>
                    <th>{teams[0]?.team ? teams[0].team : 'Team #1'}</th>
                    <th>{teams[1]?.team ? teams[1].team : 'Team #2'}</th>
                  </tr>
                </thead>
                <tbody>
                  {insightRows.map((row) => (
                    <tr key={row.label}>
                      <td className="row-label">{row.label}</td>
                      <td>{row.render(teams[0])}</td>
                      <td>{row.render(teams[1])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

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

import { useEffect, useRef, useState } from 'react'
import './App.css'
import ComparisonTable from './components/ComparisonTable'
import InsightsTable, { type PlayerRanks } from './components/InsightsTable'
import PredictionPanel from './components/PredictionPanel'
import TeamAutocomplete from './components/TeamAutocomplete'
import { type ProgressData, ProgressStreamError, followProgress } from './progress'
import type { MatchesSummary, Statistics, StatisticsResult, TeamData } from './types'
import { useTeamInput } from './useTeamInput'
import { VERSION } from './version'

// Roster and match history window, sent to /api/statistics as `days` (same default as the backend)
const STATS_DAYS = 20

// Page tabs, kept in the URL hash so a refresh stays on the tab ("#predictions/12" is the Predictions tab too)
type Tab = 'compare' | 'predictions'
const TABS: { id: Tab; label: string }[] = [
  { id: 'compare', label: 'Compare' },
  { id: 'predictions', label: 'Predictions' },
]
const tabFromHash = (hash: string): Tab => (hash.startsWith('#predictions') ? 'predictions' : 'compare')

/**
 * Team roster (account lists) is collected indirectly:
 *    - Frontend calls: GET /api/statistics?team=Alliance&team=OG
 *    - Backend fetches team data from OpenDota API (compute_statistics() -> _create_team_stats() -> resolve_roster())
 *    - Player accounts are the players with the most tournament games in the window (stale team list as fallback)
 *    - This is a background task (players_statistics_task).
 *    - It's needed to follow progress /api/stream-progress/{task_id} and get results at /api/results/{task_id}
 */
function App() {
  const team1 = useTeamInput()
  const team2 = useTeamInput()
  const [statistics, setStatistics] = useState<Statistics | null>(null)
  const [summaryData, setSummaryData] = useState<Record<string, StatisticsResult> | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [progress, setProgress] = useState<ProgressData | null>(null)
  const [backendVersion, setBackendVersion] = useState<string | null>(null)
  const [showRawStats, setShowRawStats] = useState(false)
  const [showSummaryData, setShowSummaryData] = useState(false)
  const [tab, setTab] = useState<Tab>(() => tabFromHash(window.location.hash))
  const pollAbortRef = useRef<AbortController | null>(null)
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

  useEffect(() => {
    const onHashChange = () => setTab(tabFromHash(window.location.hash))
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  // Close open progress streams when the page goes away
  useEffect(() => () => pollAbortRef.current?.abort(), [])

  const stopPolling = () => {
    pollAbortRef.current?.abort()
    pollAbortRef.current = null
  }

  // Stop polling and show the error
  const failPolling = (message: string) => {
    setError(message)
    setLoading(false)
    stopPolling()
  }

  const handleCheck = async () => {
    if (!team1.value.trim() || !team2.value.trim()) {
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
      params.append(...team1.queryParam())
      params.append(...team2.queryParam())
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
    const controller = new AbortController()
    pollAbortRef.current = controller
    const pollTimeout = setTimeout(
      () => failPolling('Polling timeout: Task took longer than 5 minutes'),
      MAX_POLLING_TIME
    )
    controller.signal.addEventListener('abort', () => clearTimeout(pollTimeout))

    const isCurrentSearch = () => currentSearchIdRef.current === searchId
    const onProgress = (progressData: ProgressData) => {
      // Stop if a new search has started
      if (!isCurrentSearch()) controller.abort()
      else setProgress(progressData)
    }

    const ids = taskIds.filter((taskId): taskId is string => Boolean(taskId))
    let summaries: Record<string, StatisticsResult>
    try {
      // Follow all task streams at once; each line updates the progress bar as it arrives
      const finals = await Promise.all(ids.map(taskId => followProgress(taskId, controller.signal, onProgress)))
      summaries = Object.fromEntries(ids.map((taskId, i) => [taskId, finals[i].data as StatisticsResult]))
    } catch (err) {
      if (controller.signal.aborted) return
      if (err instanceof ProgressStreamError) {
        failPolling(err.message)
      } else {
        console.error('Error polling progress:', err)
        failPolling(`Polling error: ${err instanceof Error ? err.message : String(err)}`)
      }
      return
    }
    if (!isCurrentSearch()) return

    // All tasks are complete, fetch detailed results
    setLoading(false)
    stopPolling()

    // Fetch detailed results for each completed task
    try {
      const detailedResults: Record<string, StatisticsResult> = {}

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

  // Leaderboard rank per account, from the team's task results (only the players the task fetched)
  const getPlayerRanks = (team: TeamData | undefined): PlayerRanks => {
    const results = (team?.task_id && summaryData?.[team.task_id]?.results) || []
    return new Map(results.filter((r) => 'rank' in r).map((r) => [r.account_id, r.rank ?? null]))
  }

  const getSummaryForTeam = (taskId: string | null | undefined): MatchesSummary | null =>
    (taskId && summaryData?.[taskId]?.summary) || null

  const teams = [statistics?.teams?.[0], statistics?.teams?.[1]]
  const summaries = teams.map((team) => getSummaryForTeam(team?.task_id))
  const results = teams.map((team) => (team?.task_id ? summaryData?.[team.task_id] : undefined))

  return (
    <div className="container">
      <div className="app-header">
        <h1>Dota 2 Bet Analyzer</h1>
        <div className="app-versions">
          <span className="app-version-frontend">Frontend: v{VERSION}</span>
          <span className="app-version-backend">Backend: v {backendVersion || 'loading...'}</span>
        </div>
      </div>

      <nav className="tab-bar">
        {TABS.map((t) => (
          <a
            key={t.id}
            href={`#${t.id}`}
            className={`tab ${tab === t.id ? 'active' : ''}`}
            aria-current={tab === t.id ? 'page' : undefined}
          >
            {t.label}
          </a>
        ))}
      </nav>

      <div className="tab-panel" hidden={tab !== 'predictions'}>
        <p>The prediction list is coming soon.</p>
      </div>

      {/* Hidden rather than unmounted, so the loaded teams and the prediction form survive a tab switch */}
      <div className="tab-panel" hidden={tab !== 'compare'}>
        <div className="form-section">
          <div className="input-groups-row">
            <div className="input-group">
              <label htmlFor="team1">Team #1</label>
              <TeamAutocomplete
                value={team1.value}
                onChange={team1.onChange}
                onSelect={team1.onSelect}
                placeholder="Enter first team name"
                autoFocus
              />
            </div>

            <div className="input-group">
              <label htmlFor="team2">Team #2</label>
              <TeamAutocomplete
                value={team2.value}
                onChange={team2.onChange}
                onSelect={team2.onSelect}
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
                <ComparisonTable teams={teams} summaries={summaries} showSummaryRows={Boolean(summaryData)} days={STATS_DAYS} />
              </div>

              <div className="results-column">
                <h2>Team Insights</h2>
                <InsightsTable teams={teams} ranks={teams.map(getPlayerRanks)} />
              </div>
            </div>

            <PredictionPanel
              key={teams.map((team) => team?.task_id).join()}
              teams={teams}
              results={results}
              days={STATS_DAYS}
            />

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
    </div>
  )
}

export default App

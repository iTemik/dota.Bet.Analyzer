import { useCallback, useEffect, useState } from 'react'
import { formatDate } from '../format'
import { requestJson } from '../predictions'

interface TeamsSyncStatus {
  synced_at: number | null
  running: boolean
}

interface TeamsSyncResult {
  synced_at: number | null
}

// How often to re-check while a sync started elsewhere (startup) is running
export const STATUS_POLL_MS = 5000

/** Button right of the tabs that refreshes the team search list from OpenDota, with the last sync date (and the error when it fails). */
function TeamsSync() {
  const [syncedAt, setSyncedAt] = useState<number | null>(null)
  const [running, setRunning] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadStatus = useCallback(
    () =>
      requestJson<TeamsSyncStatus>('/api/teams/sync')
        .then((status) => {
          setSyncedAt(status.synced_at)
          setRunning(status.running)
        })
        .catch(() => setRunning(false)),
    [],
  )

  useEffect(() => {
    loadStatus()
  }, [loadStatus])

  // A startup sync is running: check again until it finishes
  useEffect(() => {
    if (!running) return
    const timer = setTimeout(loadStatus, STATUS_POLL_MS)
    return () => clearTimeout(timer)
  }, [running, loadStatus])

  const handleSync = async () => {
    setSyncing(true)
    setError(null)
    try {
      const data = await requestJson<TeamsSyncResult>('/api/teams/sync', { method: 'POST' })
      setSyncedAt(data.synced_at)
    } catch (err) {
      setError((err as Error).message)
      loadStatus()
    } finally {
      setSyncing(false)
    }
  }

  const busy = syncing || running
  return (
    <div className="teams-sync">
      {error && (
        <span role="alert" className="teams-sync-error">
          {error}
        </span>
      )}
      <span className="teams-sync-time">
        {syncedAt ? `Updated ${formatDate(syncedAt)}` : 'Never updated'}
      </span>
      <button type="button" onClick={handleSync} disabled={busy} className="teams-sync-btn">
        {busy ? 'Updating teams…' : 'Update teams data'}
      </button>
    </div>
  )
}

export default TeamsSync

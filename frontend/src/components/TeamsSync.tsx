import { useCallback, useEffect, useState } from 'react'
import { formatDateTime } from '../format'
import { requestJson } from '../predictions'

interface TeamsSyncStatus {
  synced_at: number | null
  running: boolean
}

interface TeamsSyncResult {
  synced_count: number
  message: string
  synced_at: number | null
}

// How often to re-check while a sync started elsewhere (startup) is running
export const STATUS_POLL_MS = 5000

/** Button that refreshes the team search list from OpenDota, with the last sync time and the result. */
function TeamsSync() {
  const [syncedAt, setSyncedAt] = useState<number | null>(null)
  const [running, setRunning] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)

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
    setResult(null)
    try {
      const data = await requestJson<TeamsSyncResult>('/api/teams/sync', { method: 'POST' })
      setSyncedAt(data.synced_at)
      setResult({ ok: true, text: data.message })
    } catch (err) {
      setResult({ ok: false, text: (err as Error).message })
      loadStatus()
    } finally {
      setSyncing(false)
    }
  }

  const busy = syncing || running
  return (
    <div className="teams-sync">
      <span className="teams-sync-time">
        Teams list: {syncedAt ? `updated ${formatDateTime(syncedAt)}` : 'never updated'}
      </span>
      <button type="button" onClick={handleSync} disabled={busy} className="teams-sync-btn">
        {busy ? 'Updating teams…' : 'Update teams list'}
      </button>
      {result && (
        <span role="status" className={result.ok ? 'teams-sync-ok' : 'teams-sync-error'}>
          {result.text}
        </span>
      )}
    </div>
  )
}

export default TeamsSync

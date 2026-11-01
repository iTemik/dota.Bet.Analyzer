import { useEffect, useState } from 'react'
import { type DataStatus as Status, type JobStatus, budgetNearLimit, followDataStatus, isBusy } from '../dataStatus'
import { formatShortDateTime } from '../format'

const statusText = (job: JobStatus): string => {
  if (job.state === 'failed') return job.last_error || job.message || 'Update failed'
  if (isBusy(job)) return job.message || `Updating ${job.title.toLowerCase()}`
  return job.message || 'Up to date'
}

const nextRunText = (job: JobStatus): string => {
  if (isBusy(job)) return '-'
  return job.next_run ? formatShortDateTime(job.next_run) : 'Now'
}

/**
 * "Data" status line under the tab bar: the state of the background cache jobs and today's OpenDota requests,
 * from GET /api/jobs/stream. Failed jobs get a Retry button; Details lists every job with a Run button.
 */
export default function DataStatus() {
  const [status, setStatus] = useState<Status | null>(null)
  const [open, setOpen] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    followDataStatus(controller.signal, setStatus)
    return () => controller.abort()
  }, [])

  if (!status) return null

  // Queue jobs now; the stream shows their progress, the answer marks them queued right away
  const runJobs = async (names: string[]) => {
    setRunError(null)
    for (const name of names) {
      try {
        const response = await fetch(`/api/jobs/${name}/run`, { method: 'POST' })
        const data = await response.json()
        if (!response.ok) {
          setRunError(data.message || `Could not start the update (HTTP ${response.status})`)
          continue
        }
        setStatus((current) =>
          current && { ...current, jobs: current.jobs.map((job) => (job.name === name ? data : job)) }
        )
      } catch (err) {
        setRunError(`Could not start the update: ${err}`)
      }
    }
  }

  const failed = status.jobs.filter((job) => job.state === 'failed')
  const busy = status.jobs.filter(isBusy)
  const running = busy.find((job) => job.state === 'running') ?? busy[0]
  const { used, limit } = status.budget
  const nearLimit = budgetNearLimit(status.budget)

  let summary: string
  let summaryClass = 'data-status-summary'
  if (failed.length > 0) {
    summary = `${failed.map((job) => job.title).join(', ')} update failed`
    summaryClass += ' data-status-failed'
  } else if (running) {
    summary = statusText(running)
    if (running.state === 'running' && running.progress > 0) summary += ` ${Math.round(running.progress)}%`
  } else {
    summary = 'Data up to date'
  }
  const lastUpdates = status.jobs
    .map((job) => `${job.title}: ${job.last_success ? formatShortDateTime(job.last_success) : 'never'}`)
    .join('\n')

  return (
    <div className="data-status" role="region" aria-label="Data status">
      <div className="data-status-line">
        <span className="data-status-label">Data</span>
        <span className={summaryClass} title={lastUpdates} data-testid="data-status-summary">
          {summary}
        </span>
        {running && running.state === 'running' && running.progress > 0 && (
          <span className="data-bar" aria-hidden="true">
            <span className="data-bar-fill" style={{ width: `${Math.min(100, running.progress)}%` }} />
          </span>
        )}
        {failed.length > 0 && (
          <button type="button" className="data-status-button" onClick={() => runJobs(failed.map((job) => job.name))}>
            Retry
          </button>
        )}
        {used !== null && (
          <span className={`data-budget${nearLimit ? ' data-budget-warn' : ''}`} data-testid="data-budget">
            <span>OpenDota today: {limit > 0 ? `${used} / ${limit}` : used}</span>
            {limit > 0 && (
              <span
                className="data-bar"
                role="progressbar"
                aria-label="OpenDota requests today"
                aria-valuemin={0}
                aria-valuemax={limit}
                aria-valuenow={used}
              >
                <span className="data-bar-fill" style={{ width: `${Math.min(100, (used / limit) * 100)}%` }} />
              </span>
            )}
          </span>
        )}
        <button
          type="button"
          className="data-status-button"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? 'Hide details' : 'Details'}
        </button>
      </div>
      {runError && <div className="data-status-failed">{runError}</div>}
      {open && (
        <table className="data-jobs" aria-label="Data jobs">
          <thead>
            <tr>
              <th>Data</th>
              <th>Status</th>
              <th>Last update</th>
              <th>Next update</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {status.jobs.map((job) => (
              <tr key={job.name}>
                <td>{job.title}</td>
                <td className={job.state === 'failed' ? 'data-status-failed' : undefined}>{statusText(job)}</td>
                <td>{job.last_success ? formatShortDateTime(job.last_success) : 'Never'}</td>
                <td>{nextRunText(job)}</td>
                <td>
                  <button
                    type="button"
                    className="data-status-button"
                    disabled={isBusy(job)}
                    aria-label={`Run ${job.title}`}
                    onClick={() => runJobs([job.name])}
                  >
                    Run
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

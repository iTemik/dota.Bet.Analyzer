import { readLines } from './progress'

// Background cache jobs and today's OpenDota budget, as sent by GET /api/jobs/stream

export type JobState = 'idle' | 'queued' | 'running' | 'failed'

export interface JobStatus {
  name: string
  title: string
  state: JobState
  progress: number
  message: string | null
  last_success: number | null
  last_error: string | null
  last_error_at: number | null
  next_run: number | null
}

export interface Budget {
  used: number | null // OpenDota requests today (UTC); null when Redis is down
  limit: number // daily budget of background jobs; 0 = no budget
}

export interface DataStatus {
  jobs: JobStatus[]
  budget: Budget
}

// The budget bar turns red from this share of the daily limit
export const BUDGET_WARN_SHARE = 0.9

export const isBusy = (job: JobStatus) => job.state === 'queued' || job.state === 'running'

export const budgetNearLimit = (budget: Budget) =>
  budget.limit > 0 && budget.used !== null && budget.used >= budget.limit * BUDGET_WARN_SHARE

/** Parse one stream line; null for anything that is not a status line (e.g. an error line). */
export function parseDataStatus(line: string): DataStatus | null {
  try {
    const parsed = JSON.parse(line) as Partial<DataStatus>
    return Array.isArray(parsed.jobs) && parsed.budget ? (parsed as DataStatus) : null
  } catch {
    return null
  }
}

export const STREAM_REOPEN_DELAY = 1000 // ms before reopening a stream that ended normally (after 120 s)
export const STREAM_RETRY_DELAY = 30000 // ms before trying again after an error or a response without status

const delay = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, ms)
    signal.addEventListener('abort', () => {
      clearTimeout(timer)
      resolve()
    }, { once: true })
  })

/**
 * Follow GET /api/jobs/stream until aborted, calling onStatus for each status line.
 * The stream is reopened when it ends; after an error or a response with no status line it waits longer.
 */
export async function followDataStatus(signal: AbortSignal, onStatus: (status: DataStatus) => void): Promise<void> {
  while (!signal.aborted) {
    let received = false
    try {
      const response = await fetch('/api/jobs/stream', { signal })
      if (response.ok) {
        await readLines(response, (line) => {
          const status = parseDataStatus(line)
          if (status && !signal.aborted) {
            received = true
            onStatus(status)
          }
        })
      }
    } catch {
      // Network error or abort: retried below unless aborted
    }
    await delay(received ? STREAM_REOPEN_DELAY : STREAM_RETRY_DELAY, signal)
  }
}

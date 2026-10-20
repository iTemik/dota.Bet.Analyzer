export interface ProgressData {
  step: number
  message: string
  progress: number
  data: unknown
  timestamp: number
}

export type ParsedProgress =
  | { ok: true; progress: ProgressData }
  | { ok: false; reason: 'empty' | 'invalid' }

/** Whether a line is a stream timeout: no change for a while, so the client should reopen the stream. */
export function isStreamTimeout(progress: ProgressData | null): boolean {
  return Boolean(progress?.data && (progress.data as { timeout?: boolean }).timeout)
}

/**
 * Parse a /api/stream-progress response (NDJSON: one JSON object per line).
 *
 * Returns the last valid progress line. Stream timeout lines only mean no new step yet
 * (e.g. waiting for the OpenDota rate limit), so they never replace an earlier real line.
 * Lines that aren't valid JSON are skipped.
 */
export function parseProgress(text: string): ParsedProgress {
  const lines = text.split('\n').filter(line => line.trim())
  if (lines.length === 0) return { ok: false, reason: 'empty' }

  let last: ProgressData | null = null
  for (const line of lines) {
    let parsed: ProgressData
    try {
      parsed = JSON.parse(line) as ProgressData
    } catch {
      continue
    }
    if (!isStreamTimeout(parsed) || !last) last = parsed
  }

  return last ? { ok: true, progress: last } : { ok: false, reason: 'invalid' }
}

/** A progress stream failure whose message is shown to the user as is. */
export class ProgressStreamError extends Error {}

const STREAM_RECONNECT_DELAY = 1000 // ms before reopening a stream that ended before the task finished
// The backend answers 404 until the worker has stored the task's first progress. Retry that for a while.
const STREAM_NOT_FOUND_RETRIES = 10

/**
 * Call onLine for each non-empty line of an NDJSON response as soon as it arrives.
 * A response without a readable body is read whole.
 */
export async function readLines(response: Response, onLine: (line: string) => void): Promise<void> {
  const reader = response.body?.getReader()
  if (!reader) {
    ;(await response.text()).split('\n').filter(line => line.trim()).forEach(onLine)
    return
  }
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    lines.filter(line => line.trim()).forEach(onLine)
  }
  buffer += decoder.decode()
  if (buffer.trim()) onLine(buffer)
}

const delay = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    if (signal.aborted) return reject(signal.reason)
    const timer = setTimeout(resolve, ms)
    signal.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(signal.reason)
    }, { once: true })
  })

/**
 * Follow a task's /api/stream-progress until the task completes, calling onProgress for each new line.
 *
 * The stream is reopened when it ends before the task finished (the backend closes idle streams).
 * Stream timeout lines are not passed to onProgress.
 *
 * A 404 is retried for a few seconds, since the worker may not have started the task yet.
 *
 * Returns the final line (progress 100). Throws ProgressStreamError when the request fails,
 * the response has no usable lines or the task failed (progress -1), and the abort reason when aborted.
 */
export async function followProgress(
  taskId: string,
  signal: AbortSignal,
  onProgress: (progress: ProgressData) => void
): Promise<ProgressData> {
  let notFoundCount = 0
  for (;;) {
    const response = await fetch(`/api/stream-progress/${taskId}`, { signal })
    if (response.status === 404 && notFoundCount < STREAM_NOT_FOUND_RETRIES) {
      notFoundCount += 1
      await delay(STREAM_RECONNECT_DELAY, signal)
      continue
    }
    if (!response.ok) {
      throw new ProgressStreamError(`Failed to fetch progress for task ${taskId}: HTTP ${response.status}`)
    }
    notFoundCount = 0

    let lineCount = 0
    let validCount = 0
    let last: ProgressData | null = null
    try {
      await readLines(response, line => {
        lineCount += 1
        const parsed = parseProgress(line)
        if (!parsed.ok) return
        validCount += 1
        if (isStreamTimeout(parsed.progress)) return
        last = parsed.progress
        onProgress(parsed.progress)
      })
    } catch (readError) {
      if (signal.aborted) throw signal.reason
      throw new ProgressStreamError(`Failed to read response for task ${taskId}: ${readError}`)
    }

    if (lineCount === 0) throw new ProgressStreamError(`No data found in response for task ${taskId}`)
    if (validCount === 0) throw new ProgressStreamError(`No valid JSON found in response for task ${taskId}`)
    const final = last as ProgressData | null
    if (final?.progress === -1) throw new ProgressStreamError(final.message)
    if (final && final.progress >= 100) return final

    await delay(STREAM_RECONNECT_DELAY, signal)
  }
}

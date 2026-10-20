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
    const isStreamTimeout = parsed?.data && (parsed.data as { timeout?: boolean }).timeout
    if (!isStreamTimeout || !last) last = parsed
  }

  return last ? { ok: true, progress: last } : { ok: false, reason: 'invalid' }
}

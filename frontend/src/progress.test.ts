import { describe, expect, it } from 'vitest'
import { parseProgress } from './progress'

const line = (obj: unknown) => JSON.stringify(obj)
const step1 = { step: 1, message: 'Fetching matches', progress: 10, data: {}, timestamp: 1 }
const step2 = { step: 2, message: 'Fetching players', progress: 50, data: {}, timestamp: 2 }
const timeout = { step: -1, message: 'Task timed out', progress: -1, data: { error: true, timeout: true } }

describe('parseProgress', () => {
  it('returns the last valid line', () => {
    expect(parseProgress(`${line(step1)}\n${line(step2)}\n`)).toEqual({ ok: true, progress: step2 })
  })

  it('keeps the last real line when a stream timeout follows it', () => {
    expect(parseProgress(`${line(step1)}\n${line(timeout)}\n`)).toEqual({ ok: true, progress: step1 })
  })

  it('returns a stream timeout when it is the only line', () => {
    expect(parseProgress(line(timeout))).toEqual({ ok: true, progress: timeout })
  })

  it('skips lines that are not valid JSON', () => {
    expect(parseProgress(`${line(step1)}\nnot json\n`)).toEqual({ ok: true, progress: step1 })
  })

  it('reports an empty response', () => {
    expect(parseProgress('')).toEqual({ ok: false, reason: 'empty' })
    expect(parseProgress('\n  \n')).toEqual({ ok: false, reason: 'empty' })
  })

  it('reports a response with no valid JSON', () => {
    expect(parseProgress('oops\n{broken')).toEqual({ ok: false, reason: 'invalid' })
  })
})

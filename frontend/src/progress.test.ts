import { afterEach, describe, expect, it, vi } from 'vitest'
import { type ProgressData, ProgressStreamError, followProgress, parseProgress, readLines } from './progress'

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

/** A streamed response that sends each chunk only when the test calls push(). */
function controlledStream() {
  let controller!: ReadableStreamDefaultController<Uint8Array>
  const body = new ReadableStream<Uint8Array>({ start: c => { controller = c } })
  const encoder = new TextEncoder()
  return {
    response: new Response(body),
    push: (text: string) => controller.enqueue(encoder.encode(text)),
    close: () => controller.close(),
  }
}

const streamResponse = (text: string) => Promise.resolve(new Response(text))
const done = { step: 3, message: 'Complete', progress: 100, data: { successful: 1 }, timestamp: 3 }

describe('readLines', () => {
  it('passes each line on as soon as it is complete, even when split across chunks', async () => {
    const stream = controlledStream()
    const lines: string[] = []
    const reading = readLines(stream.response, l => lines.push(l))

    stream.push(`${line(step1)}\n${line(step2).slice(0, 10)}`)
    await vi.waitFor(() => expect(lines).toEqual([line(step1)]))

    stream.push(`${line(step2).slice(10)}\n\n${line(done)}`)
    stream.close()
    await reading
    expect(lines).toEqual([line(step1), line(step2), line(done)])
  })

  it('reads a response without a readable body as a whole', async () => {
    const lines: string[] = []
    const response = { body: null, text: () => Promise.resolve(`${line(step1)}\n\n${line(step2)}\n`) }
    await readLines(response as unknown as Response, l => lines.push(l))
    expect(lines).toEqual([line(step1), line(step2)])
  })
})

describe('followProgress', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('reports each line as it arrives and returns the final line', async () => {
    const stream = controlledStream()
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(stream.response)))
    const seen: ProgressData[] = []

    const following = followProgress('task_1', new AbortController().signal, p => seen.push(p))
    stream.push(`${line(step1)}\n`)
    await vi.waitFor(() => expect(seen).toEqual([step1]))
    stream.push(`${line(done)}\n`)
    stream.close()

    await expect(following).resolves.toEqual(done)
    expect(seen).toEqual([step1, done])
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('reopens the stream after an idle timeout without reporting the timeout line', async () => {
    vi.useFakeTimers()
    const fetchMock = vi
      .fn()
      .mockReturnValueOnce(streamResponse(`${line(step1)}\n${line(timeout)}\n`))
      .mockReturnValueOnce(streamResponse(`${line(step1)}\n${line(done)}\n`))
    vi.stubGlobal('fetch', fetchMock)
    const seen: ProgressData[] = []

    const following = followProgress('task_1', new AbortController().signal, p => seen.push(p))
    await vi.waitFor(() => expect(seen).toEqual([step1]))
    expect(fetchMock).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1000)

    await expect(following).resolves.toEqual(done)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(seen).toEqual([step1, step1, done])
  })

  it('fails with the task error message when the task fails', async () => {
    const failed = { step: -1, message: 'Task error: boom', progress: -1, data: { error: true } }
    vi.stubGlobal('fetch', vi.fn(() => streamResponse(`${line(step1)}\n${line(failed)}\n`)))

    await expect(followProgress('task_1', new AbortController().signal, () => {})).rejects.toEqual(
      new ProgressStreamError('Task error: boom')
    )
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('fails on an HTTP error, an empty response and a response with no valid JSON', async () => {
    const signal = new AbortController().signal
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('', { status: 500 }))))
    await expect(followProgress('t', signal, () => {})).rejects.toThrow('Failed to fetch progress for task t: HTTP 500')

    vi.stubGlobal('fetch', vi.fn(() => streamResponse('')))
    await expect(followProgress('t', signal, () => {})).rejects.toThrow('No data found in response for task t')

    vi.stubGlobal('fetch', vi.fn(() => streamResponse('oops\n')))
    await expect(followProgress('t', signal, () => {})).rejects.toThrow('No valid JSON found in response for task t')
  })

  it('stops waiting to reopen the stream when aborted', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn(() => streamResponse(`${line(timeout)}\n`))
    vi.stubGlobal('fetch', fetchMock)
    const controller = new AbortController()

    const following = followProgress('task_1', controller.signal, () => {})
    const outcome = expect(following).rejects.toThrow()
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    controller.abort()
    await outcome
    await vi.advanceTimersByTimeAsync(5000)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})

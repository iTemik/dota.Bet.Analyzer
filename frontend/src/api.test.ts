import { afterEach, describe, expect, it, vi } from 'vitest'
import { patchJson, postJson, putJson, requestJson } from './api'

const respond = (status: number, body?: unknown) =>
  vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: body === undefined ? () => Promise.reject(new Error('no body')) : () => Promise.resolve(body),
  })

describe('api', () => {
  const realFetch = globalThis.fetch
  afterEach(() => {
    globalThis.fetch = realFetch
  })

  it('returns the parsed JSON', async () => {
    globalThis.fetch = respond(200, { a: 1 }) as unknown as typeof fetch
    await expect(requestJson('/api/x')).resolves.toEqual({ a: 1 })
  })

  it('returns null for 204 No Content', async () => {
    globalThis.fetch = respond(204) as unknown as typeof fetch
    await expect(requestJson('/api/x', { method: 'DELETE' })).resolves.toBeNull()
  })

  it("throws with the backend's message", async () => {
    globalThis.fetch = respond(404, { status: 404, code: 'TEAM_NOT_FOUND', message: 'Team not found' }) as unknown as typeof fetch
    await expect(requestJson('/api/x')).rejects.toThrow('Team not found')
  })

  it('throws with the status when the body has no message', async () => {
    globalThis.fetch = respond(500) as unknown as typeof fetch
    await expect(requestJson('/api/x')).rejects.toThrow('HTTP error! status: 500')
  })

  it.each([
    ['POST', postJson],
    ['PUT', putJson],
    ['PATCH', patchJson],
  ] as const)('sends a %s JSON body', async (method, send) => {
    const fetchMock = respond(200, { ok: true })
    globalThis.fetch = fetchMock as unknown as typeof fetch
    await expect(send('/api/x', { b: 2 })).resolves.toEqual({ ok: true })
    expect(fetchMock).toHaveBeenCalledWith('/api/x', {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: '{"b":2}',
    })
  })
})

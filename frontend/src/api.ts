// The one fetch helper for the backend API: every JSON request goes through requestJson

type JsonMethod = 'POST' | 'PUT' | 'PATCH'

// Fetch JSON; throws with the backend's message on an error status. Returns null for 204 No Content
export const requestJson = async <T>(url: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(url, init)
  const data = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) throw new Error(data?.message || `HTTP error! status: ${response.status}`)
  return data as T
}

// Send a JSON body with the given method; returns the response JSON or throws with the backend's message
const sendJson = <T>(method: JsonMethod, url: string, body: unknown): Promise<T> =>
  requestJson<T>(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const postJson = <T>(url: string, body: unknown): Promise<T> => sendJson<T>('POST', url, body)
export const putJson = <T>(url: string, body: unknown): Promise<T> => sendJson<T>('PUT', url, body)
export const patchJson = <T>(url: string, body: unknown): Promise<T> => sendJson<T>('PATCH', url, body)

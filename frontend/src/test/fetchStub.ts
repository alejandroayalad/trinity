/**
 * Replace window.fetch with contract-shaped responses for one test.
 *
 * Tests that use this stub are O evidence only (spec, Verification): they
 * prove frontend behavior against synthetic responses, not the real API.
 * Every request is recorded so a test can check what was sent, for example
 * that a guarded page sent no request at all.
 */
import { vi } from 'vitest'

export type RecordedRequest = {
  method: string
  /** Path without the query, for example "/api/v1/me". */
  path: string
  search: URLSearchParams
  url: string
  headers: Headers
  body: unknown
}

type Reply = Response | ((request: RecordedRequest) => Response | Promise<Response>)

/** Map "METHOD /path" to a reply. A list gives one reply per call, in order; the last one repeats. */
export type Routes = Record<string, Reply | Reply[]>

export function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': '11111111-2222-4333-8444-555555555555', ...headers },
  })
}

/** A problem document in the backend's exact shape (backend/src/trinity/errors.py). */
export function problem(status: number, code: string, extra: Record<string, unknown> = {}, headers: Record<string, string> = {}): Response {
  return new Response(
    JSON.stringify({
      type: 'about:blank',
      title: 'Error',
      status,
      detail: 'Error',
      code,
      request_id: '99999999-8888-4777-8666-555555555555',
      errors: [],
      blocker: null,
      current_revision: null,
      ...extra,
    }),
    { status, headers: { 'Content-Type': 'application/problem+json', ...headers } },
  )
}

export function stubFetch(routes: Routes): { calls: RecordedRequest[] } {
  const calls: RecordedRequest[] = []
  const counters = new Map<string, number>()

  vi.stubGlobal('fetch', async (input: string, init: RequestInit = {}) => {
    const url = new URL(input, 'http://localhost')
    const method = (init.method ?? 'GET').toUpperCase()
    const body = typeof init.body === 'string' ? (JSON.parse(init.body) as unknown) : undefined
    const recorded: RecordedRequest = {
      method,
      path: url.pathname,
      search: url.searchParams,
      url: input,
      headers: new Headers(init.headers),
      body,
    }
    calls.push(recorded)

    const key = `${method} ${url.pathname}`
    const route = routes[key]
    if (route === undefined) throw new Error(`Unexpected request in test: ${key}`)
    const index = counters.get(key) ?? 0
    counters.set(key, index + 1)
    const reply = Array.isArray(route) ? route[Math.min(index, route.length - 1)] : route
    const response = typeof reply === 'function' ? await reply(recorded) : reply
    // A Response body can be read once. Clone it so a repeated route still works.
    return response.clone()
  })

  return { calls }
}

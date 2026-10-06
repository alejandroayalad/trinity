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
  /** The cancel signal the client passed, or null. A test asserts aborts on it. */
  signal: AbortSignal | null
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

/**
 * Reject with the browser's AbortError as soon as the signal aborts. A
 * pending reply promise cannot resolve afterwards, which is how the real
 * fetch behaves when the caller cancels.
 */
function withAbort<T>(value: T | Promise<T>, signal: AbortSignal | null | undefined): Promise<T> {
  if (signal == null) return Promise.resolve(value)
  return new Promise<T>((resolve, reject) => {
    const abort = () => reject(new DOMException('Aborted', 'AbortError'))
    if (signal.aborted) {
      abort()
      return
    }
    signal.addEventListener('abort', abort, { once: true })
    Promise.resolve(value).then(
      (result) => { signal.removeEventListener('abort', abort); resolve(result) },
      // Pass an upstream failure through unchanged. A non-Error reason cannot
      // come from the stub, which replies with Response or Error values.
      (error: unknown) => { signal.removeEventListener('abort', abort); reject(error instanceof Error ? error : new Error('fetch stub reply failed')) },
    )
  })
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
      signal: init.signal ?? null,
    }
    calls.push(recorded)

    const key = `${method} ${url.pathname}`
    const route = routes[key]
    if (route === undefined) throw new Error(`Unexpected request in test: ${key}`)
    const index = counters.get(key) ?? 0
    counters.set(key, index + 1)
    const reply = Array.isArray(route) ? route[Math.min(index, route.length - 1)] : route
    const response = await withAbort(typeof reply === 'function' ? reply(recorded) : reply, init.signal)
    // A Response body can be read once. Clone it so a repeated route still works.
    return response.clone()
  })

  return { calls }
}

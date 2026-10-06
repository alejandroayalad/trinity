import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { saveSession } from '../session/session'
import { json, problem, stubFetch } from '../test/fetchStub'
import { ApiError, request, setPublicationListener, setUnauthorizedHandler } from './client'
import { errorMessage } from './messages'

// A synthetic 43-character token in the backend's token format. It is not a real credential.
const TOKEN = 'synthetic-test-token-0123456789abcdefghijkl'

function signIn() {
  saveSession({ accessToken: TOKEN, expiresAt: new Date(Date.now() + 3_600_000).toISOString() })
}

async function failure(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise
  } catch (error) {
    if (error instanceof ApiError) return error
    throw error
  }
  throw new Error('Expected the request to fail.')
}

describe('API client', () => {
  beforeEach(() => {
    setUnauthorizedHandler(null)
    setPublicationListener(null)
  })

  afterEach(() => {
    setUnauthorizedHandler(null)
    setPublicationListener(null)
  })

  it('sends the bearer token only in the Authorization header, never in the URL', async () => {
    signIn()
    const { calls } = stubFetch({ 'GET /api/v1/catalog': json(200, { publication: null }) })
    await request('GET', '/catalog', { query: { start: '2026-09-01', end: undefined } })
    expect(calls[0].headers.get('Authorization')).toBe(`Bearer ${TOKEN}`)
    expect(calls[0].url).toBe('/api/v1/catalog?start=2026-09-01')
    expect(calls[0].url).not.toContain(TOKEN)
  })

  it('sends no Authorization header for sign-in and no cookies at all', async () => {
    signIn()
    const fetchSpy = vi.fn(() => Promise.resolve(json(200, {})))
    vi.stubGlobal('fetch', fetchSpy)
    await request('POST', '/auth/login', { body: { username: 'admin', password: 'x' }, authenticated: false })
    const [, init] = fetchSpy.mock.calls[0] as unknown as [string, RequestInit]
    expect(new Headers(init.headers).has('Authorization')).toBe(false)
    expect(init.credentials).toBe('omit')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
  })

  it('returns data with ETag, Location and request ID headers', async () => {
    signIn()
    stubFetch({
      'POST /api/v1/refresh-runs': json(202, { run_id: 'r' }, { ETag: '"run-1"', Location: '/api/v1/refresh-runs/r' }),
    })
    const result = await request('POST', '/refresh-runs', { body: {}, idempotencyKey: 'key-1' })
    expect(result.status).toBe(202)
    expect(result.etag).toBe('"run-1"')
    expect(result.location).toBe('/api/v1/refresh-runs/r')
    expect(result.requestId).toBe('11111111-2222-4333-8444-555555555555')
  })

  it('sends If-Match and Idempotency-Key for commands and no body for the warning DELETE', async () => {
    signIn()
    const { calls } = stubFetch({ 'DELETE /api/v1/refresh-runs/r/warning': json(200, {}) })
    await request('DELETE', '/refresh-runs/r/warning', { ifMatch: '"run-3"', idempotencyKey: 'key-2' })
    expect(calls[0].headers.get('If-Match')).toBe('"run-3"')
    expect(calls[0].headers.get('Idempotency-Key')).toBe('key-2')
    expect(calls[0].body).toBeUndefined()
    expect(calls[0].headers.has('Content-Type')).toBe(false)
  })

  it.each([
    [400, 'invalid_json'],
    [415, 'unsupported_media_type'],
    [422, 'sql_not_allowed'],
    [403, 'forbidden'],
    [404, 'dataset_not_found'],
    [409, 'data_unavailable'],
    [412, 'revision_mismatch'],
    [428, 'precondition_required'],
    [413, 'request_too_large'],
    [500, 'internal_error'],
    [503, 'dependency_unavailable'],
    [504, 'query_timeout'],
  ])('decodes a %i problem with code %s', async (status, code) => {
    signIn()
    stubFetch({ 'GET /api/v1/catalog': problem(status, code) })
    const error = await failure(request('GET', '/catalog'))
    expect(error.status).toBe(status)
    expect(error.code).toBe(code)
    expect(error.requestId).toBe('99999999-8888-4777-8666-555555555555')
  })

  it('keeps Retry-After seconds and the blocker of a problem', async () => {
    signIn()
    const blocker = { code: 'failure_unresolved', message: 'Review the failed refresh.', run_id: 'r', version_id: null, warning_id: 'w' }
    stubFetch({
      'POST /api/v1/queries': problem(429, 'rate_limited', {}, { 'Retry-After': '17' }),
      'POST /api/v1/refresh-runs': problem(409, 'refresh_blocked', { blocker }),
    })
    const limited = await failure(request('POST', '/queries', { body: { sql: 'SELECT 1' } }))
    expect(limited.retryAfter).toBe(17)
    expect(errorMessage(limited)).toBe('Too many requests. Try again in 17 seconds.')
    const blocked = await failure(request('POST', '/refresh-runs', { body: {}, idempotencyKey: 'k' }))
    expect(blocked.blocker).toEqual(blocker)
  })

  it('turns a non-problem error page into internal_error without showing its text', async () => {
    signIn()
    stubFetch({
      'GET /api/v1/catalog': new Response('<html>Proxy error: secret-looking text</html>', {
        status: 502,
        headers: { 'Content-Type': 'text/html', 'X-Request-ID': 'req-1' },
      }),
    })
    const error = await failure(request('GET', '/catalog'))
    expect(error.code).toBe('internal_error')
    expect(errorMessage(error)).toBe('Something went wrong. Request ID: req-1.')
    expect(errorMessage(error)).not.toContain('secret-looking')
  })

  it('reports a network failure as status 0 so only those requests are retried', async () => {
    signIn()
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')))
    const error = await failure(request('GET', '/me'))
    expect(error.isNetworkError).toBe(true)
    expect(error.code).toBe('network_error')
  })

  it('ends the session on a 401 to an authenticated request, and does not retry it', async () => {
    signIn()
    const ended = vi.fn()
    setUnauthorizedHandler(ended)
    const { calls } = stubFetch({ 'GET /api/v1/me': problem(401, 'invalid_session', {}, { 'WWW-Authenticate': 'Bearer' }) })
    const error = await failure(request('GET', '/me'))
    expect(error.code).toBe('invalid_session')
    expect(ended).toHaveBeenCalledTimes(1)
    expect(calls).toHaveLength(1)
  })

  it('does not end a session for a failed sign-in or for sign-out', async () => {
    signIn()
    const ended = vi.fn()
    setUnauthorizedHandler(ended)
    stubFetch({
      'POST /api/v1/auth/login': problem(401, 'invalid_credentials'),
      'POST /api/v1/auth/logout': problem(401, 'invalid_session'),
    })
    await failure(request('POST', '/auth/login', { body: {}, authenticated: false }))
    await failure(request('POST', '/auth/logout', { body: {}, skipSessionEnd: true }))
    expect(ended).not.toHaveBeenCalled()
  })

  it('reports each publication it sees so stale queries can refresh', async () => {
    signIn()
    const seen = vi.fn()
    setPublicationListener(seen)
    stubFetch({
      'GET /api/v1/me': json(200, { publication: { publication_event_id: 'event-2' } }),
      'GET /api/v1/catalog': json(200, { publication: null }),
      'GET /api/v1/settings': json(200, { revision: '1' }),
    })
    await request('GET', '/me')
    await request('GET', '/catalog')
    await request('GET', '/settings')
    expect(seen.mock.calls).toEqual([['event-2'], [null]])
  })

  it('never writes to the console, so tokens and passwords cannot reach logs', async () => {
    signIn()
    const spies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((name) =>
      vi.spyOn(console, name).mockImplementation(() => undefined),
    )
    stubFetch({ 'POST /api/v1/auth/login': problem(401, 'invalid_credentials'), 'GET /api/v1/me': json(200, {}) })
    await failure(request('POST', '/auth/login', { body: { username: 'admin', password: 'synthetic-pass' }, authenticated: false }))
    await request('GET', '/me')
    for (const spy of spies) expect(spy).not.toHaveBeenCalled()
  })
})

/**
 * The one HTTP client for the Trinity API.
 *
 * Every request in the app goes through `request`. It builds a relative
 * /api/v1 URL, adds the bearer token from the session, sends JSON and reads
 * the response. A failure becomes an ApiError with the server's stable error
 * code, so pages map codes to messages instead of parsing raw responses.
 *
 * Side effects, in order:
 * 1. A 401 to a request that carried a token ends the session once, through
 *    the handler that SessionProvider registers. The request is not retried.
 * 2. A response that contains `publication` reports its publication_event_id
 *    to the publication listener, which refreshes stale queries (spec R31).
 *
 * The client never logs, and never puts the token in a URL or an error.
 */
import { getAccessToken } from '../session/session'
import type { Blocker, FieldError } from './types'

type Method = 'GET' | 'POST' | 'PUT' | 'DELETE'

export type RequestOptions = {
  /** Query parameters. An undefined value is left out; an empty string is sent. */
  query?: Record<string, string | undefined>
  /** JSON body. Commands with no fields send `{}`; the warning DELETE sends none. */
  body?: unknown
  ifMatch?: string
  idempotencyKey?: string
  /** False for sign-in, which has no session yet. */
  authenticated?: boolean
  /** True for sign-out: a 401 then needs no "session ended" message. */
  skipSessionEnd?: boolean
  signal?: AbortSignal
}

export type ApiResult<T> = {
  data: T
  status: number
  etag: string | null
  location: string | null
  requestId: string | null
}

type ApiErrorFields = {
  status: number
  code: string
  detail?: string
  requestId?: string | null
  retryAfter?: number | null
  blocker?: Blocker | null
  currentRevision?: string | null
  fieldErrors?: FieldError[]
}

/**
 * A failed API call. `status` is 0 when no HTTP response arrived. `code` is
 * the server's stable code, `network_error` without a response, or
 * `internal_error` when the response was not a valid problem document.
 */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly detail: string
  readonly requestId: string | null
  readonly retryAfter: number | null
  readonly blocker: Blocker | null
  readonly currentRevision: string | null
  readonly fieldErrors: FieldError[]

  constructor(fields: ApiErrorFields) {
    super(`API request failed: ${fields.code}`)
    this.name = 'ApiError'
    this.status = fields.status
    this.code = fields.code
    this.detail = fields.detail ?? ''
    this.requestId = fields.requestId ?? null
    this.retryAfter = fields.retryAfter ?? null
    this.blocker = fields.blocker ?? null
    this.currentRevision = fields.currentRevision ?? null
    this.fieldErrors = fields.fieldErrors ?? []
  }

  get isNetworkError(): boolean {
    return this.status === 0
  }
}

export function isApiError(error: unknown, code?: string): error is ApiError {
  return error instanceof ApiError && (code === undefined || error.code === code)
}

let unauthorizedHandler: (() => void) | null = null
let publicationListener: ((publicationEventId: string | null) => void) | null = null

/** SessionProvider registers the function that clears the session on a 401. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler
}

/** The query setup registers the function that reacts to a publication change. */
export function setPublicationListener(listener: ((publicationEventId: string | null) => void) | null): void {
  publicationListener = listener
}

function buildUrl(path: string, query: RequestOptions['query']): string {
  const params = new URLSearchParams()
  for (const [name, value] of Object.entries(query ?? {})) {
    if (value !== undefined) params.append(name, value)
  }
  const search = params.toString()
  return `/api/v1${path}${search ? `?${search}` : ''}`
}

/** Read Retry-After as whole seconds. Ignore any form other than digits. */
function parseRetryAfter(value: string | null): number | null {
  if (value === null || !/^\d{1,6}$/.test(value)) return null
  return Number.parseInt(value, 10)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * Turn an error response into an ApiError. A problem document must have a
 * text `code`; anything else (an HTML proxy page, broken JSON) becomes
 * `internal_error` with the request ID, and its raw text is never shown.
 */
async function readProblem(response: Response, headerRequestId: string | null): Promise<ApiError> {
  const retryAfter = parseRetryAfter(response.headers.get('Retry-After'))
  let body: unknown = null
  if ((response.headers.get('Content-Type') ?? '').includes('json')) {
    try {
      body = await response.json()
    } catch {
      body = null
    }
  }
  if (isRecord(body) && typeof body.code === 'string') {
    return new ApiError({
      status: response.status,
      code: body.code,
      detail: typeof body.detail === 'string' ? body.detail : '',
      requestId: typeof body.request_id === 'string' ? body.request_id : headerRequestId,
      retryAfter,
      blocker: isRecord(body.blocker) ? (body.blocker as Blocker) : null,
      currentRevision: typeof body.current_revision === 'string' ? body.current_revision : null,
      fieldErrors: Array.isArray(body.errors) ? (body.errors as FieldError[]) : [],
    })
  }
  return new ApiError({ status: response.status, code: 'internal_error', requestId: headerRequestId, retryAfter })
}

/** Report the publication of an analytical response, if it has one. */
function reportPublication(data: unknown): void {
  if (publicationListener === null || !isRecord(data) || !('publication' in data)) return
  const publication = data.publication
  if (publication === null) {
    publicationListener(null)
  } else if (isRecord(publication) && typeof publication.publication_event_id === 'string') {
    publicationListener(publication.publication_event_id)
  }
}

export async function request<T>(method: Method, path: string, options: RequestOptions = {}): Promise<ApiResult<T>> {
  const headers = new Headers({ Accept: 'application/json' })
  if (options.body !== undefined) headers.set('Content-Type', 'application/json')
  if (options.ifMatch !== undefined) headers.set('If-Match', options.ifMatch)
  if (options.idempotencyKey !== undefined) headers.set('Idempotency-Key', options.idempotencyKey)
  const token = options.authenticated === false ? null : getAccessToken()
  if (token !== null) headers.set('Authorization', `Bearer ${token}`)

  let response: Response
  try {
    response = await fetch(buildUrl(path, options.query), {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      // The token travels only in the Authorization header. No cookie is sent.
      credentials: 'omit',
      cache: 'no-store',
      signal: options.signal,
    })
  } catch (error) {
    // A cancelled request stays an AbortError so the query library ignores it.
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError({ status: 0, code: 'network_error' })
  }

  const requestId = response.headers.get('X-Request-ID')
  if (!response.ok) {
    const error = await readProblem(response, requestId)
    // Ignore a denial from authority already cleared or replaced locally.
    // SessionProvider separately handles expiry of its current startup check.
    if (response.status === 401 && token !== null && !options.skipSessionEnd
        && getAccessToken() === token) unauthorizedHandler?.()
    throw error
  }

  let data: unknown = null
  if (response.status !== 204) {
    try {
      data = await response.json()
    } catch {
      throw new ApiError({ status: response.status, code: 'internal_error', requestId })
    }
  }
  if (token === null || getAccessToken() === token) reportPublication(data)
  return {
    data: data as T,
    status: response.status,
    etag: response.headers.get('ETag'),
    location: response.headers.get('Location'),
    requestId,
  }
}

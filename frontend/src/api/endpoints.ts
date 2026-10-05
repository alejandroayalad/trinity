/**
 * One typed function per API operation. Pages call these functions, never
 * fetch, so every request shares the client's token, error and header rules.
 */
import { request } from './client'
import type {
  ActionReceipt,
  Candidate,
  CatalogResponse,
  DatasetKey,
  LoginResponse,
  MeResponse,
  PreviewResponse,
  QueryResponse,
  Run,
  RunList,
  SettingsResponse,
} from './types'

const path = (value: string) => encodeURIComponent(value)

export function login(username: string, password: string) {
  return request<LoginResponse>('POST', '/auth/login', { body: { username, password }, authenticated: false })
}

export function logout() {
  return request<null>('POST', '/auth/logout', { body: {}, skipSessionEnd: true })
}

export function getMe() {
  return request<MeResponse>('GET', '/me')
}

export function getCatalog() {
  return request<CatalogResponse>('GET', '/catalog')
}

/** Filters that preview accepts. A missing value uses the server default. */
export type PreviewFilters = {
  start?: string
  end?: string
  facility?: string
  generator?: string
}

export function getPreview(datasetKey: DatasetKey, filters: PreviewFilters, limit: number, cursor?: string) {
  return request<PreviewResponse>('GET', `/datasets/${path(datasetKey)}/preview`, {
    query: { ...filters, limit: String(limit), cursor },
  })
}

export function runQuery(sql: string, signal?: AbortSignal) {
  return request<QueryResponse>('POST', '/queries', { body: { sql }, signal })
}

export function getRuns(cursor?: string) {
  return request<RunList>('GET', '/refresh-runs', { query: { cursor } })
}

export function getRun(runId: string, stepsCursor?: string) {
  return request<Run>('GET', `/refresh-runs/${path(runId)}`, { query: { steps_cursor: stepsCursor } })
}

export function startRefresh(idempotencyKey: string) {
  return request<ActionReceipt>('POST', '/refresh-runs', { body: {}, idempotencyKey })
}

export function getCandidate(versionId: string) {
  return request<Candidate>('GET', `/candidates/${path(versionId)}`)
}

export type CandidateCommand = 'approval' | 'publication-retry' | 'discard'

export function sendCandidateCommand(versionId: string, command: CandidateCommand, etag: string, idempotencyKey: string) {
  return request<ActionReceipt>('POST', `/candidates/${path(versionId)}/${command}`, {
    body: {},
    ifMatch: etag,
    idempotencyKey,
  })
}

export function getSettings() {
  return request<SettingsResponse>('GET', '/settings')
}

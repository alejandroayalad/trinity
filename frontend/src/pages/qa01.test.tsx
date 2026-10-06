/**
 * QA-01 request handling checks.
 *
 * The checks prove the client contract against synthetic responses (O
 * evidence): cancellation reaches fetch, dates need Apply, choices load on
 * first open, and errors offer a Retry. The Playwright regression against the
 * real API is separate (R evidence).
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import { afterEach, expect, test, vi } from 'vitest'
import { SessionProvider } from '../session/SessionProvider'
import { clearSession, saveSession } from '../session/session'
import { App } from '../App'
import { json, problem, stubFetch, type RecordedRequest } from '../test/fetchStub'
import { shouldRetry, retryDelay } from '../api/retry'
import { ApiError } from '../api/client'
import type { CatalogResponse, MeResponse, PreviewResponse, Publication } from '../api/types'

const publication: Publication = { publication_event_id: 'event', version_id: 'version', published_at: '2026-10-03T00:00:00Z', coverage_start: '2026-10-01', coverage_end: '2026-10-02', latest_observation_date: '2026-10-02' }
const me: MeResponse = { user_id: 'test', role: 'analyst', capabilities: ['national:read', 'preview:detail', 'sql:execute', 'catalog:read'], data_ready: true, landing_screen: 'explorer', publication, admin_context: null }
const columns: PreviewResponse['columns'] = [{ name: 'period', type: 'date', nullable: false, unit: null }, { name: 'capacity', type: 'decimal', nullable: false, unit: 'MW' }, { name: 'outage', type: 'decimal', nullable: false, unit: 'MW' }, { name: 'percentOutage', type: 'decimal', nullable: true, unit: 'percent' }]
const catalog: CatalogResponse = { datasets: [{ key: 'national_outages', label: 'National outages', description: 'National', daily_key: ['period'], columns, available_filters: ['start', 'end'] }], metrics: [], data_ready: true, publication, freshness: { latest_observation_date: '2026-10-02', published_at: publication.published_at, last_refresh: null } }
const page: PreviewResponse = { publication, dataset_key: 'national_outages', range: { start: '2026-10-01', end: '2026-10-02' }, columns, rows: [['2026-10-01', '100', '10', null]], returned_rows: 1, next_cursor: null, reason: null, diagnostics: [] }
const summary = { period: '2026-10-02', capacity: '100', outage: '102.4', percentOutage: null, offline_share_percent: '102.40', reason: null }
const dashboardBody = { publication, range: page.range, days: [summary], summary, diagnostics: [], freshness: catalog.freshness }

afterEach(() => { clearSession(); vi.useRealTimers() })

/** The /me capability set stays small so Dashboard renders no contribution reads. */
function mount(path: string, initialize?: (cache: QueryClient) => void) {
  saveSession({ accessToken: 'synthetic', expiresAt: '2099-01-01T00:00:00Z' })
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  initialize?.(cache)
  render(<QueryClientProvider client={cache}><MemoryRouter initialEntries={[path]}><SessionProvider><App /></SessionProvider></MemoryRouter></QueryClientProvider>)
}

const isDashboard = (call: RecordedRequest) => call.path.endsWith('/dashboard/national')

test('three rapid preset clicks cancel the older requests and render the last preset', async () => {
  // The first replies never settle. Only an abort can release them, which is
  // exactly what a superseded query must do.
  const pending = () => new Promise<Response>(() => undefined)
  const { calls } = stubFetch({
    'GET /api/v1/me': json(200, { ...me, capabilities: ['national:read'] }),
    'GET /api/v1/dashboard/national': [pending, pending, pending, json(200, dashboardBody)],
  })
  mount('/dashboard')
  await waitFor(() => expect(calls.filter(isDashboard)).toHaveLength(1))
  fireEvent.click(screen.getByRole('button', { name: 'Last 365 days' }))
  await waitFor(() => expect(calls.filter(isDashboard)).toHaveLength(2))
  fireEvent.click(screen.getByRole('button', { name: '90 days' }))
  await waitFor(() => expect(calls.filter(isDashboard)).toHaveLength(3))
  fireEvent.click(screen.getByRole('button', { name: '30 days' }))
  await screen.findByRole('heading', { name: 'Range end observation · 2026-10-02' })
  const dashboardCalls = calls.filter(isDashboard)
  expect(dashboardCalls).toHaveLength(4)
  expect(dashboardCalls.slice(0, 3).map((call) => call.signal?.aborted)).toEqual([true, true, true])
  expect(dashboardCalls[3].signal?.aborted).toBe(false)
})

test('catalog dates wait for Apply and Reset clears the draft', async () => {
  const { calls } = stubFetch({
    'GET /api/v1/me': json(200, me),
    'GET /api/v1/catalog': json(200, catalog),
    'GET /api/v1/datasets/national_outages/preview': json(200, page),
  })
  mount('/catalog/national_outages')
  await screen.findByText('1 rows · Combined share: 10.00%')
  const previews = () => calls.filter((call) => call.path.endsWith('/preview'))
  expect(previews()).toHaveLength(1)
  fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-01-01' } })
  fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-01-31' } })
  await act(async () => { await Promise.resolve() })
  expect(previews()).toHaveLength(1)
  fireEvent.click(screen.getByRole('button', { name: 'Apply dates' }))
  await waitFor(() => expect(previews()).toHaveLength(2))
  expect(previews()[1].search.get('start')).toBe('2026-01-01')
  expect(previews()[1].search.get('end')).toBe('2026-01-31')
  fireEvent.click(screen.getByRole('button', { name: 'Reset filters' }))
  expect(screen.getByLabelText('From')).toHaveValue('')
  expect(screen.getByLabelText('To')).toHaveValue('')
})

test('facility choices load only when the control first opens', async () => {
  const { calls } = stubFetch({
    'GET /api/v1/me': json(200, me),
    'GET /api/v1/catalog': json(200, catalog),
    'GET /api/v1/datasets/facility_outages/preview': json(200, { ...page, dataset_key: 'facility_outages' }),
    'GET /api/v1/datasets/facility_outages/facilities': json(200, { publication, range: page.range, items: [{ facility: '0046', facilityName: 'Example Plant' }], next_cursor: null }),
  })
  mount('/catalog/facility_outages')
  await screen.findByText('1 rows · Combined share: 10.00%')
  const facilities = () => calls.filter((call) => call.path.endsWith('/facilities'))
  expect(facilities()).toHaveLength(0)
  fireEvent.focus(screen.getByLabelText('Search facilities'))
  await waitFor(() => expect(facilities()).toHaveLength(1))
  await screen.findByRole('option', { name: 'Example Plant (0046)' })
})

test('a 429 shows Retry and the click refetches', async () => {
  const { calls } = stubFetch({
    'GET /api/v1/me': json(200, { ...me, capabilities: ['national:read'] }),
    'GET /api/v1/dashboard/national': [problem(429, 'rate_limited', {}, { 'Retry-After': '30' }), json(200, dashboardBody)],
  })
  mount('/dashboard')
  await screen.findByText('Too many requests. Try again in 30 seconds.')
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  await screen.findByRole('heading', { name: 'Range end observation · 2026-10-02' })
  expect(calls.filter(isDashboard)).toHaveLength(2)
})

test('a rate limit with a short wait retries once and recovers', async () => {
  const { calls } = stubFetch({
    'GET /api/v1/me': json(200, { ...me, capabilities: ['national:read'] }),
    'GET /api/v1/dashboard/national': [problem(429, 'rate_limited', {}, { 'Retry-After': '1' }), json(200, dashboardBody)],
  })
  mount('/dashboard', (cache) => { cache.setDefaultOptions({ queries: { retry: shouldRetry, retryDelay, refetchOnWindowFocus: false } }) })
  await screen.findByRole('heading', { name: 'Range end observation · 2026-10-02' }, { timeout: 3000 })
  expect(calls.filter(isDashboard)).toHaveLength(2)
})

test('a 503 stays failed and offers a manual Retry', async () => {
  const { calls } = stubFetch({
    'GET /api/v1/me': json(200, { ...me, capabilities: ['national:read'] }),
    'GET /api/v1/dashboard/national': problem(503, 'service_unavailable'),
  })
  mount('/dashboard', (cache) => { cache.setDefaultOptions({ queries: { retry: shouldRetry, retryDelay, refetchOnWindowFocus: false } }) })
  await screen.findByRole('button', { name: 'Retry' })
  expect(calls.filter(isDashboard)).toHaveLength(1)
})

test('the automatic retry rule accepts one short rate-limit wait only', () => {
  const rateLimited = (retryAfter: number | null) => new ApiError({ status: 429, code: 'rate_limited', retryAfter })
  expect(shouldRetry(0, rateLimited(1))).toBe(true)
  expect(shouldRetry(1, rateLimited(1))).toBe(false)
  expect(shouldRetry(0, rateLimited(30))).toBe(false)
  expect(shouldRetry(0, rateLimited(null))).toBe(false)
  expect(shouldRetry(0, new ApiError({ status: 503, code: 'service_unavailable' }))).toBe(false)
  expect(retryDelay(0, rateLimited(2))).toBe(2000)
})

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import { afterEach, expect, test, vi } from 'vitest'
import { SessionProvider } from '../session/SessionProvider'
import { clearSession, saveSession } from '../session/session'
import { App } from '../App'
import { json, problem, stubFetch, type RecordedRequest } from '../test/fetchStub'
import type { CatalogResponse, MeResponse, PreviewResponse, Publication } from '../api/types'
import { PageError } from './shared'
import { ApiError } from '../api/client'
import { shouldRetry, retryDelay } from '../api/retry'
import { FacilityChoices } from './catalog/Choices'

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

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}
const previewCalls = (calls: RecordedRequest[]) => calls.filter((c) => c.path.endsWith('/preview'))
const baseRoutes = { 'GET /api/v1/me': json(200, me), 'GET /api/v1/catalog': json(200, catalog) }

test('search debounces terms, cancels old answers, and never displays a delayed old selection', async () => {
  const old = deferred<Response>()
  const { calls } = stubFetch({ 'GET /api/v1/datasets/facility_outages/facilities': (call) => call.search.get('search') === 'old' ? old.promise : json(200, { publication, items: [{ facility: '0046', facilityName: call.search.get('search') ?? 'initial' }], next_cursor: null }) })
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><FacilityChoices dataset="facility_outages" filters={{}} onChange={() => undefined} /></QueryClientProvider>)
  fireEvent.focus(screen.getByLabelText('Search facilities'))
  await screen.findByRole('option', { name: 'initial (0046)' })
  vi.useFakeTimers()
  for (const value of ['o', 'ol', 'old']) fireEvent.change(screen.getByLabelText('Search facilities'), { target: { value } })
  await act(async () => { await vi.advanceTimersByTimeAsync(299) })
  expect(calls).toHaveLength(1)
  await act(async () => { await vi.advanceTimersByTimeAsync(1) })
  expect(calls).toHaveLength(2)
  fireEvent.change(screen.getByLabelText('Search facilities'), { target: { value: 'latest' } })
  expect(calls[1].signal?.aborted).toBe(true)
  await act(async () => { await vi.advanceTimersByTimeAsync(300) })
  await act(async () => { await vi.advanceTimersByTimeAsync(1) })
  vi.useRealTimers()
  await screen.findByRole('option', { name: 'latest (0046)' })
  await act(async () => { await Promise.resolve(); old.resolve(json(200, { publication, items: [{ facility: 'old', facilityName: 'obsolete' }], next_cursor: null })) })
  expect(screen.queryByRole('option', { name: /obsolete/ })).not.toBeInTheDocument()
  expect(calls.map((c) => c.search.get('search'))).toEqual([null, 'old', 'latest'])
})

test('Reset cancels pending debounce, clears linked filters, and leaves unopened generator choices lazy', async () => {
  const { calls } = stubFetch({ ...baseRoutes,
    'GET /api/v1/datasets/generator_outages/preview': json(200, page),
    'GET /api/v1/datasets/generator_outages/facilities': json(200, { publication, items: [{ facility: '0046', facilityName: 'old choice' }], next_cursor: null }),
  })
  mount('/catalog/generator_outages?facility=0046')
  await screen.findByText('Combined offline share for these rows: 10 MW ÷ 100 MW = 10.00% (summed outage ÷ summed capacity).')
  expect(screen.getByLabelText('Facility')).toHaveValue('0046')
  expect(calls.some((c) => c.path.endsWith('/generators'))).toBe(false)
  fireEvent.focus(screen.getByLabelText('Search facilities'))
  await screen.findByRole('option', { name: 'old choice (0046)' })
  vi.useFakeTimers()
  fireEvent.change(screen.getByLabelText('Search facilities'), { target: { value: 'old search' } })
  fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-01-01' } })
  fireEvent.click(screen.getByRole('button', { name: 'Reset filters' }))
  await act(async () => { await vi.advanceTimersByTimeAsync(500) })
  vi.useRealTimers()
  expect(screen.getByLabelText('Search facilities')).toHaveValue('')
  expect(screen.getByLabelText('Facility')).toHaveValue('')
  expect(screen.getByLabelText('From')).toHaveValue('')
  expect(screen.queryByRole('option', { name: /old choice/ })).not.toBeInTheDocument()
  expect(calls.filter((c) => c.path.endsWith('/facilities'))).toHaveLength(1)
  expect(previewCalls(calls).at(-1)?.search.has('facility')).toBe(false)
})

test('returning to a cached paginated filter starts with one page and stops obsolete Load all', async () => {
  const obsolete = deferred<Response>()
  const { calls } = stubFetch({ ...baseRoutes, 'GET /api/v1/datasets/national_outages/preview': (call) => {
    const cursor = call.search.get('cursor')
    if (cursor === 'third') return obsolete.promise
    return json(200, { ...page, next_cursor: cursor ? 'third' : 'second' })
  } })
  mount('/catalog/national_outages')
  await screen.findByText('Showing 1 rows. Load all rows to calculate the combined share.')
  fireEvent.click(screen.getByRole('button', { name: 'Load more' }))
  await screen.findByText('Showing 2 rows. Load all rows to calculate the combined share.')
  fireEvent.click(screen.getByRole('button', { name: 'Load all rows' }))
  await waitFor(() => expect(previewCalls(calls)).toHaveLength(3))
  fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-01-01' } })
  fireEvent.click(screen.getByRole('button', { name: 'Apply dates' }))
  await waitFor(() => expect(previewCalls(calls)).toHaveLength(4))
  expect(previewCalls(calls)[2].signal?.aborted).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Reset filters' }))
  await screen.findByText('Showing 1 rows. Load all rows to calculate the combined share.')
  await act(async () => { await Promise.resolve(); obsolete.resolve(json(200, { ...page, next_cursor: 'fourth' })) })
  expect(previewCalls(calls).map((c) => c.search.get('cursor'))).toEqual([null, 'second', 'third', null, null])
  expect(screen.getByRole('button', { name: 'Load all rows' })).toBeEnabled()
})

test('dashboard announces refetching, ignores late data and retries only current parameters once per click burst', async () => {
  const old = deferred<Response>(), retry = deferred<Response>()
  const { calls } = stubFetch({
    'GET /api/v1/me': json(200, { ...me, role: 'viewer', capabilities: ['national:read'] }),
    'GET /api/v1/dashboard/national': [json(200, dashboardBody), () => old.promise, problem(503, 'dependency_unavailable'), () => retry.promise],
  })
  mount('/dashboard')
  await screen.findByText('Selected range loaded.')
  fireEvent.click(screen.getByRole('button', { name: '90 days' }))
  expect(screen.getByText(/Updating range. Showing previous data/)).toHaveTextContent('Showing previous data')
  expect(screen.getByText(/Updating range. Showing previous data/)).toHaveAttribute('aria-live', 'polite')
  expect(document.querySelector('[aria-busy="true"]')).not.toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Last 365 days' }))
  const button = await screen.findByRole('button', { name: 'Retry' })
  fireEvent.click(button); fireEvent.click(button)
  await waitFor(() => expect(calls.filter(isDashboard)).toHaveLength(4))
  expect(button).toBeDisabled()
  expect(calls.filter(isDashboard).at(-1)?.search.get('preset')).toBe('1y')
  await act(async () => { await Promise.resolve(); retry.resolve(json(200, dashboardBody)); old.resolve(json(200, { ...dashboardBody, summary: { ...summary, period: 'obsolete' } })) })
  await screen.findByText('Selected range loaded.')
  expect(screen.queryByText(/observation · obsolete/)).not.toBeInTheDocument()
  expect(calls.filter(isDashboard)[1].signal?.aborted).toBe(true)
  expect(calls.some((c) => /facility|generator/.test(c.path))).toBe(false)
})

test('choice publication changes restart at page one without mixed options', async () => {
  const { calls } = stubFetch({ 'GET /api/v1/datasets/facility_outages/facilities': [
    json(200, { publication, items: [{ facility: '001', facilityName: 'old' }], next_cursor: 'next' }),
    problem(409, 'publication_changed'),
    json(200, { publication: { ...publication, publication_event_id: 'new' }, items: [{ facility: '002', facilityName: 'new' }], next_cursor: null }),
  ] })
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><FacilityChoices dataset="facility_outages" filters={{}} onChange={() => undefined} /></QueryClientProvider>)
  fireEvent.focus(screen.getByLabelText('Search facilities'))
  fireEvent.click(await screen.findByRole('button', { name: 'More facilities' }))
  await screen.findByRole('option', { name: 'new (002)' })
  expect(screen.queryByRole('option', { name: 'old (001)' })).not.toBeInTheDocument()
  expect(calls.map((c) => c.search.get('cursor'))).toEqual([null, 'next', null])
})

test('manual recovery observes Retry-After and rejects duplicate clicks with controlled time', async () => {
  vi.useFakeTimers()
  const pending = deferred<void>(), retry = vi.fn(() => pending.promise)
  render(<PageError error={new ApiError({ status: 429, code: 'rate_limited', retryAfter: 30 })} onRetry={retry} />)
  fireEvent.click(screen.getByRole('button', { name: 'Retry after 30s' }))
  expect(retry).not.toHaveBeenCalled()
  await act(async () => { await vi.advanceTimersByTimeAsync(29999) })
  expect(screen.getByRole('button')).toBeDisabled()
  await act(async () => { await vi.advanceTimersByTimeAsync(1) })
  fireEvent.click(screen.getByRole('button', { name: 'Retry' })); fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  expect(retry).toHaveBeenCalledTimes(1)
  await act(async () => { pending.resolve(); await pending.promise })
})

test.each(['forbidden', 'data_unavailable'])('%s never offers blind read retry', (code) => {
  render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><SessionProvider><PageError error={new ApiError({ status: code === 'forbidden' ? 403 : 409, code })} onRetry={vi.fn()} /></SessionProvider></MemoryRouter></QueryClientProvider>)
  expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
})

test('an exhausted automatic 429 retry stays bounded at two requests', async () => {
  const { calls } = stubFetch({ 'GET /api/v1/me': json(200, { ...me, capabilities: ['national:read'] }), 'GET /api/v1/dashboard/national': problem(429, 'rate_limited', {}, { 'Retry-After': '0' }) })
  mount('/dashboard', (cache) => cache.setDefaultOptions({ queries: { retry: shouldRetry, retryDelay } }))
  await screen.findByRole('button', { name: 'Retry' })
  expect(calls.filter(isDashboard)).toHaveLength(2)
})

test('preview Retry uses the latest applied filters and does not duplicate active recovery', async () => {
  const pending = deferred<Response>()
  const { calls } = stubFetch({ ...baseRoutes, 'GET /api/v1/datasets/national_outages/preview': [problem(503, 'dependency_unavailable'), problem(503, 'dependency_unavailable'), () => pending.promise] })
  mount('/catalog/national_outages')
  await screen.findByRole('button', { name: 'Retry' })
  fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-10-01' } })
  fireEvent.click(screen.getByRole('button', { name: 'Apply dates' }))
  const retry = await screen.findByRole('button', { name: 'Retry' })
  fireEvent.click(retry); fireEvent.click(retry)
  await waitFor(() => expect(previewCalls(calls)).toHaveLength(3))
  expect(previewCalls(calls).at(-1)?.search.get('start')).toBe('2026-10-01')
  await act(async () => { pending.resolve(json(200, page)); await pending.promise })
  await screen.findByText('Combined offline share for these rows: 10 MW ÷ 100 MW = 10.00% (summed outage ÷ summed capacity).')
})

test('facility Retry recovers the current search', async () => {
  const { calls } = stubFetch({ 'GET /api/v1/datasets/facility_outages/facilities': [problem(503, 'dependency_unavailable'), json(200, { publication, items: [{ facility: '0001', facilityName: 'Recovered' }], next_cursor: null })] })
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><FacilityChoices dataset="facility_outages" filters={{}} onChange={() => undefined} /></QueryClientProvider>)
  fireEvent.focus(screen.getByLabelText('Search facilities'))
  fireEvent.click(await screen.findByRole('button', { name: 'Retry' }))
  await screen.findByRole('option', { name: 'Recovered (0001)' })
  expect(calls).toHaveLength(2)
  expect(calls[1].search.toString()).toBe(calls[0].search.toString())
})

test('contribution Retry recovers the selected day', async () => {
  const { calls } = stubFetch({ ...baseRoutes,
    'GET /api/v1/dashboard/national': json(200, { ...dashboardBody, days: [{ ...summary, period: '2026-10-01' }, summary] }),
    'GET /api/v1/datasets/facility_outages/preview': [problem(503, 'dependency_unavailable'), json(200, { ...page, rows: [], next_cursor: null })],
  })
  mount('/dashboard')
  fireEvent.click(await screen.findByRole('button', { name: 'Retry' }))
  await screen.findByRole('heading', { name: 'Facility outage contributions 2 Oct 2026' })
  expect(previewCalls(calls)).toHaveLength(2)
  expect(previewCalls(calls).every((c) => c.search.get('start') === summary.period && c.search.get('end') === summary.period)).toBe(true)
})

test('Reset aborts in-flight choices and a late response cannot restore them', async () => {
  const pending = deferred<Response>()
  const { calls } = stubFetch({ ...baseRoutes,
    'GET /api/v1/datasets/facility_outages/preview': json(200, page),
    'GET /api/v1/datasets/facility_outages/facilities': () => pending.promise,
  })
  mount('/catalog/facility_outages')
  await screen.findByText('Combined offline share for these rows: 10 MW ÷ 100 MW = 10.00% (summed outage ÷ summed capacity).')
  fireEvent.focus(screen.getByLabelText('Search facilities'))
  await waitFor(() => expect(calls.some((c) => c.path.endsWith('/facilities'))).toBe(true))
  fireEvent.click(screen.getByRole('button', { name: 'Reset filters' }))
  expect(calls.find((c) => c.path.endsWith('/facilities'))?.signal?.aborted).toBe(true)
  await act(async () => { pending.resolve(json(200, { publication, items: [{ facility: 'obsolete', facilityName: 'obsolete' }], next_cursor: null })); await pending.promise })
  expect(screen.queryByRole('option', { name: /obsolete/ })).not.toBeInTheDocument()
  expect(screen.getByLabelText('Search facilities')).toHaveValue('')
})

test('changing parent facility clears an exact linked generator without eagerly fetching generators', async () => {
  const { calls } = stubFetch({ ...baseRoutes,
    'GET /api/v1/datasets/generator_outages/preview': json(200, page),
    'GET /api/v1/datasets/generator_outages/facilities': json(200, { publication, items: [{ facility: '0002', facilityName: 'Second' }], next_cursor: null }),
  })
  mount('/catalog/generator_outages?facility=0001&generator=01')
  await screen.findByText('Combined offline share for these rows: 10 MW ÷ 100 MW = 10.00% (summed outage ÷ summed capacity).')
  expect(screen.getByLabelText('Generator')).toHaveValue('01')
  expect(previewCalls(calls)[0].search.get('generator')).toBe('01')
  fireEvent.focus(screen.getByLabelText('Facility'))
  await screen.findByRole('option', { name: 'Second (0002)' })
  fireEvent.change(screen.getByLabelText('Facility'), { target: { value: '0002' } })
  await waitFor(() => expect(previewCalls(calls)).toHaveLength(2))
  expect(screen.getByLabelText('Generator')).toHaveValue('')
  expect(previewCalls(calls)[1].search.get('facility')).toBe('0002')
  expect(previewCalls(calls)[1].search.has('generator')).toBe(false)
  expect(calls.some((c) => c.path.endsWith('/generators'))).toBe(false)
})

test('a publication error on the first choice page does not loop automatically', async () => {
  const { calls } = stubFetch({ 'GET /api/v1/datasets/facility_outages/facilities': problem(409, 'publication_changed') })
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><FacilityChoices dataset="facility_outages" filters={{}} onChange={() => undefined} /></QueryClientProvider>)
  fireEvent.focus(screen.getByLabelText('Search facilities'))
  await screen.findByRole('button', { name: 'Retry' })
  expect(calls).toHaveLength(1)
  expect(screen.queryByText('Data changed. Restarting choices.')).not.toBeInTheDocument()
})

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import { afterEach, expect, test, vi } from 'vitest'
import { SessionProvider } from '../session/SessionProvider'
import { clearSession, saveSession } from '../session/session'
import { App } from '../App'
import { json, problem, stubFetch } from '../test/fetchStub'
import type { CatalogResponse, MeResponse, Publication, PreviewResponse } from '../api/types'
import { retryCommand } from './refresh/Refresh'
import { ApiError } from '../api/client'
import { NationalChart } from './dashboard/NationalChart'
import { GeneratorChoices } from './catalog/Choices'
import { setMediaMatches } from '../test/setup'
import { Diagnostics } from './shared'

const publication: Publication = { publication_event_id: 'event', version_id: 'version', published_at: '2026-10-03T00:00:00Z', coverage_start: '2026-10-01', coverage_end: '2026-10-02', latest_observation_date: '2026-10-02' }
const me: MeResponse = { user_id: 'test', role: 'analyst', capabilities: ['national:read', 'preview:detail', 'sql:execute', 'catalog:read'], data_ready: true, landing_screen: 'explorer', publication, admin_context: null }
const columns: PreviewResponse['columns'] = [{ name: 'period', type: 'date', nullable: false, unit: null }, { name: 'capacity', type: 'decimal', nullable: false, unit: 'MW' }, { name: 'outage', type: 'decimal', nullable: false, unit: 'MW' }, { name: 'percentOutage', type: 'decimal', nullable: true, unit: 'percent' }]
const catalog: CatalogResponse = { datasets: [{ key: 'national_outages', label: 'National outages', description: 'National', daily_key: ['period'], columns, available_filters: ['start', 'end'] }], metrics: [], data_ready: true, publication, freshness: { latest_observation_date: '2026-10-02', published_at: publication.published_at, last_refresh: null } }
const page: PreviewResponse = { publication, dataset_key: 'national_outages', range: { start: '2026-10-01', end: '2026-10-02' }, columns, rows: [['2026-10-01', '100', '10', null]], returned_rows: 1, next_cursor: 'next', reason: null, diagnostics: [] }
afterEach(() => { clearSession(); vi.useRealTimers() })
function mount(path: string, initialize?: (cache: QueryClient) => void) {
  saveSession({ accessToken: 'synthetic', expiresAt: '2099-01-01T00:00:00Z' })
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  initialize?.(cache)
  render(<QueryClientProvider client={cache}><MemoryRouter initialEntries={[path]}><SessionProvider><App /></SessionProvider></MemoryRouter></QueryClientProvider>)
}
test('table waits for all pages, then weights capacities rather than averaging shares', async () => {
  stubFetch({ 'GET /api/v1/me': json(200, me), 'GET /api/v1/catalog': json(200, catalog), 'GET /api/v1/datasets/national_outages/preview': [json(200, page), json(200, { ...page, rows: [['2026-10-02', '900', '90', '9']], next_cursor: null })] })
  mount('/catalog/national_outages')
  await screen.findByText('Showing 1 rows. Load all rows to calculate the combined share.')
  expect(screen.queryByText(/Combined share:/)).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Load more' }))
  await screen.findByText('2 rows · Combined share: 10.00%')
  expect(screen.getByText('○ Not reported')).toBeInTheDocument()
})
test('publication change drops old rows before restarting the first page', async () => {
  const { calls } = stubFetch({ 'GET /api/v1/me': json(200, me), 'GET /api/v1/catalog': json(200, catalog), 'GET /api/v1/datasets/national_outages/preview': [json(200, page), problem(409, 'publication_changed'), json(200, { ...page, rows: [['2026-10-02', '200', '40', null]], next_cursor: null })] })
  mount('/catalog/national_outages'); await screen.findByRole('button', { name: 'Load more' }); fireEvent.click(screen.getByRole('button', { name: 'Load more' }))
  await screen.findByText('The data was updated. The table restarted from the first page.')
  await screen.findByText('1 rows · Combined share: 20.00%')
  expect(screen.queryByText('2026-10-01')).not.toBeInTheDocument()
  expect(calls.filter((c) => c.path.endsWith('/preview')).at(-1)?.search.has('cursor')).toBe(false)
})
test('SQL renders exact strings and NULL without claiming missing observations', async () => {
  stubFetch({ 'GET /api/v1/me': json(200, me), 'GET /api/v1/catalog': json(200, catalog), 'POST /api/v1/queries': json(200, { publication, columns: [{ name: 'value', type: 'decimal', nullable: true, unit: 'MW' }], rows: [['999999999999999999.000001'], [null]], returned_rows: 2, truncated: true, execution_ms: 12, diagnostics: [] }) })
  mount('/sql'); fireEvent.click(await screen.findByRole('button', { name: 'Run query' }))
  await screen.findByText('999999999999999999.000001'); expect(screen.getByText('NULL')).toBeInTheDocument()
  expect(screen.getByText(/Showing the first 1,000/)).toBeInTheDocument()
})
test('SQL sends nothing when UTF-8 text exceeds the byte limit', async () => {
  const { calls } = stubFetch({ 'GET /api/v1/me': json(200, me), 'GET /api/v1/catalog': json(200, catalog) })
  mount('/sql'); fireEvent.change(await screen.findByLabelText('Query'), { target: { value: 'é'.repeat(8200) } })
  expect(screen.getByRole('button', { name: 'Run query' })).toBeDisabled()
  expect(calls.some((c) => c.method === 'POST')).toBe(false)
})
test('SQL data-unavailable response shows the waiting state without Admin controls', async () => {
  stubFetch({ 'GET /api/v1/me': json(200, me), 'GET /api/v1/catalog': json(200, catalog), 'POST /api/v1/queries': problem(409, 'data_unavailable') })
  mount('/sql'); fireEvent.click(await screen.findByRole('button', { name: 'Run query' }))
  await screen.findByText('Nothing to show yet'); expect(screen.queryByText('Go to Refresh')).not.toBeInTheDocument()
})
test('command network retry retains one key while application failures do not retry', async () => {
  const send = vi.fn().mockRejectedValueOnce(new ApiError({ status: 0, code: 'network_error' })).mockResolvedValueOnce({ data: {} })
  await retryCommand(send, 'one-confirmation')
  expect(send.mock.calls).toEqual([['one-confirmation'], ['one-confirmation']])
  const denied = vi.fn().mockRejectedValue(new ApiError({ status: 412, code: 'revision_mismatch' }))
  await expect(retryCommand(denied, 'new-confirmation')).rejects.toThrow()
  expect(denied).toHaveBeenCalledTimes(1)
})
test('chart keyboard pins calendar gaps and keeps out-of-range values visible', async () => {
  const onSelect = vi.fn()
  render(<NationalChart selected={null} onSelect={onSelect} days={[
    { period: '2026-10-01', capacity: '100', outage: '120', percentOutage: null, offline_share_percent: '120.00', reason: null },
    { period: '2026-10-02', capacity: null, outage: null, percentOutage: null, offline_share_percent: null, reason: 'not_reported' },
  ]} />)
  const plot = screen.getByRole('application'); fireEvent.keyDown(plot, { key: 'ArrowRight' }); fireEvent.keyDown(plot, { key: 'Enter' })
  expect(onSelect).toHaveBeenLastCalledWith('2026-10-02')
  fireEvent.keyDown(plot, { key: 'Escape' }); expect(onSelect).toHaveBeenLastCalledWith(null)
  await waitFor(() => expect(screen.getAllByText(/120.00%/).length).toBeGreaterThan(0))
})

test('candidate revision conflict reloads evidence and requires another review', async () => {
  const admin = { ...me, role: 'admin', capabilities: [...me.capabilities, 'refresh:read', 'candidate:review'] }
  const run = { run_id: 'run', run_seq: '4', revision: '1', requested_at: '2026-10-03T00:00:00Z', status: 'awaiting_approval', candidate: { version_id: 'candidate' }, warning: null, actions: [], steps: [], next_steps_cursor: null, poll_after_seconds: null }
  const candidate = { version_id: 'candidate', validation: { passed_required_count: 16, expected_required_count: 16 }, diagnostics: [], review_status: 'required', publication: { status: 'not_started' }, actions: [{ action: 'approve', enabled: true, reason_code: null }] }
  const { calls } = stubFetch({ 'GET /api/v1/me': json(200, admin), 'GET /api/v1/refresh-runs/run': json(200, run), 'GET /api/v1/candidates/candidate': [json(200, candidate, { ETag: '"candidate-1"' }), json(200, { ...candidate, review_status: 'approved', actions: [] }, { ETag: '"candidate-2"' })], 'POST /api/v1/candidates/candidate/approval': problem(412, 'revision_mismatch') })
  mount('/refresh/run')
  fireEvent.click(await screen.findByRole('button', { name: 'Approve' }))
  const dialog = screen.getByRole('dialog')
  fireEvent.click(dialog.querySelector('button:last-child') as HTMLButtonElement)
  await screen.findByText('This candidate changed. Review it again.')
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  const command = calls.find((c) => c.method === 'POST')
  expect(command?.headers.get('If-Match')).toBe('"candidate-1"')
  expect(command?.headers.get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/)
  expect(calls.filter((c) => c.path.endsWith('/candidates/candidate')).length).toBe(2)
})

test('settings stale revision reloads instead of overwriting another Admin edit', async () => {
  const admin = { ...me, role: 'admin', capabilities: [...me.capabilities, 'settings:read', 'settings:write'] }
  const settings = { setup_completed_at: '2026-10-01T00:00:00Z', schedule_enabled: true, daily_time: '06:00', timezone: 'UTC', revision: '1', updated_at: '2026-10-01T00:00:00Z', updated_by: 'test' }
  stubFetch({ 'GET /api/v1/me': json(200, admin), 'GET /api/v1/settings': [json(200, settings, { ETag: '"settings-1"' }), json(200, { ...settings, daily_time: '08:00', revision: '2' }, { ETag: '"settings-2"' })], 'GET /api/v1/settings/schedule-status': json(200, { next_check_local: null, blocker: null }), 'PUT /api/v1/settings': problem(412, 'revision_mismatch') })
  mount('/settings'); fireEvent.change(await screen.findByLabelText('Time'), { target: { value: '07:00' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save schedule' }))
  await screen.findByText('Settings changed in another session. Review and save again.')
  expect(screen.getByLabelText('Time')).toHaveValue('08:00')
  expect(screen.getByRole('button', { name: 'Save schedule' })).toBeDisabled()
})

test('disabled candidate actions stay hidden even when validation details exist', async () => {
  const admin = { ...me, role: 'admin', capabilities: [...me.capabilities, 'refresh:read'] }
  stubFetch({ 'GET /api/v1/me': json(200, admin), 'GET /api/v1/refresh-runs/run': json(200, { run_id: 'run', run_seq: '1', revision: '1', requested_at: publication.published_at, status: 'failed', candidate: { version_id: 'candidate' }, warning: null, actions: [], steps: [], next_steps_cursor: null, poll_after_seconds: null }), 'GET /api/v1/candidates/candidate': json(200, { version_id: 'candidate', validation: { passed_required_count: 15, expected_required_count: 16 }, diagnostics: [], review_status: 'not_ready', publication: { status: 'blocked' }, actions: [{ action: 'approve', enabled: false, reason_code: 'candidate_ineligible' }] }) })
  mount('/refresh/run'); await screen.findByText('15 / 16 required checks passed')
  expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Run again' })).not.toBeInTheDocument()
})

test('SQL rate-limit countdown prevents another request until Retry-After expires', async () => {
  const { calls } = stubFetch({ 'GET /api/v1/me': json(200, me), 'GET /api/v1/catalog': json(200, catalog), 'POST /api/v1/queries': problem(429, 'rate_limited', {}, { 'Retry-After': '2' }) })
  mount('/sql'); const run = await screen.findByRole('button', { name: 'Run query' })
  vi.useFakeTimers()
  await act(async () => { fireEvent.click(run); await vi.advanceTimersByTimeAsync(0) })
  expect(screen.getByRole('button', { name: 'Try again in 2s' })).toBeDisabled()
  await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
  expect(screen.getByRole('button', { name: 'Try again in 1s' })).toBeDisabled()
  await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
  expect(screen.getByRole('button', { name: 'Run query' })).toBeEnabled()
  expect(calls.filter((c) => c.method === 'POST')).toHaveLength(1)
})

test('dashboard distinguishes zero capacity and rejects invalid custom ranges before sending', async () => {
  setMediaMatches(['(prefers-reduced-motion: reduce)'])
  const previous = { period: '2026-10-01', capacity: '0', outage: '0', percentOutage: null, offline_share_percent: null, reason: 'zero_capacity' }
  const summary = { period: '2026-10-02', capacity: '100', outage: '102.4', percentOutage: null, offline_share_percent: '102.40', reason: null }
  const { calls } = stubFetch({ 'GET /api/v1/me': json(200, { ...me, capabilities: ['national:read'] }), 'GET /api/v1/dashboard/national': json(200, { publication, range: page.range, days: [previous, summary], summary, diagnostics: [], freshness: catalog.freshness }) })
  mount('/dashboard')
  await screen.findByText('Previous-day share (2026-10-01) is unavailable: zero capacity.')
  expect(screen.getAllByText(/102.40%/).length).toBeGreaterThan(0)
  expect(screen.getAllByText(/Out of range/).length).toBeGreaterThan(0)
  fireEvent.click(screen.getByRole('button', { name: 'Custom range' }))
  fireEvent.change(screen.getByLabelText('From'), { target: { value: '2025-01-01' } })
  fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-01-02' } })
  expect(screen.getByRole('button', { name: 'Apply range' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('To'), { target: { value: '2024-12-31' } })
  expect(screen.getByRole('button', { name: 'Apply range' })).toBeDisabled()
  expect(calls.filter((c) => c.path.endsWith('/dashboard/national'))).toHaveLength(1)
  expect(calls.some((c) => c.path.includes('facility_outages'))).toBe(false)
})

test('generator choices never combine pages from different publications', async () => {
  stubFetch({ 'GET /api/v1/datasets/generator_outages/generators': [json(200, { publication, items: [{ generator: '01' }], next_cursor: 'next' }), json(200, { publication: { ...publication, publication_event_id: 'new' }, items: [{ generator: '02' }], next_cursor: null })] })
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><GeneratorChoices filters={{ facility: '001' }} onChange={() => undefined} /></QueryClientProvider>)
  fireEvent.focus(screen.getByLabelText('Generator'))
  fireEvent.click(await screen.findByRole('button', { name: 'More generators' }))
  await screen.findByRole('option', { name: '02' })
  expect(screen.queryByRole('option', { name: '01' })).not.toBeInTheDocument()
  expect(screen.getByRole('option', { name: '02' })).toBeInTheDocument()
})

test('an explicit facility link overrides filters retained from an earlier visit', async () => {
  const { calls } = stubFetch({ 'GET /api/v1/me': json(200, me), 'GET /api/v1/catalog': json(200, catalog), 'GET /api/v1/datasets/facility_outages/preview': json(200, { ...page, dataset_key: 'facility_outages', rows: [], next_cursor: null }), 'GET /api/v1/datasets/facility_outages/facilities': json(200, { publication, items: [], next_cursor: null }) })
  mount('/catalog/facility_outages?facility=001a', (cache) => cache.setQueryData(['filters', 'facility_outages'], { facility: 'old', start: '2020-01-01' }))
  await screen.findByText('No rows match these filters.')
  const request = calls.find((c) => c.path.endsWith('/preview'))
  expect(request?.search.get('facility')).toBe('001a')
  expect(request?.search.has('start')).toBe(false)
})

// These page tests cross the API client boundary with synthetic responses.
// The command must cause the state change before a subsequent GET can show it.
for (const action of [
  { name: 'rerun', label: 'Run again', method: 'POST', suffix: 'rerun', target: 'replacement' },
  { name: 'delete_warning', label: 'Resolve warning', method: 'DELETE', suffix: 'warning', target: 'failed-run' },
]) {
  test(`enabled recovery ${action.name} sends the command and displays the resulting run`, async () => {
    const admin = { ...me, role: 'admin', capabilities: [...me.capabilities, 'refresh:read', 'refresh:recover'] }
    const run = { run_id: 'failed-run', run_seq: '4', revision: '7', requested_at: publication.published_at, status: 'failed', candidate: null, warning: null, actions: [{ action: action.name, enabled: true, reason_code: null }], steps: [], next_steps_cursor: null, poll_after_seconds: null }
    let accepted = false
    const commandPath = `/api/v1/refresh-runs/failed-run/${action.suffix}`
    const { calls } = stubFetch({
      'GET /api/v1/me': json(200, admin),
      'GET /api/v1/refresh-runs/failed-run': () => json(200, accepted ? { ...run, revision: '8', actions: [] } : run, { ETag: accepted ? '"run-8"' : '"run-7"' }),
      'GET /api/v1/refresh-runs/replacement': () => {
        expect(accepted).toBe(true)
        return json(200, { ...run, run_id: 'replacement', run_seq: '5', status: 'requested', actions: [] })
      },
      [`${action.method} ${commandPath}`]: () => {
        accepted = true
        return json(202, { operation_id: 'operation', action: action.name, accepted_at: publication.published_at, run_id: action.target, version_id: null, status_url: `/api/v1/refresh-runs/${action.target}`, result: action.name === 'rerun' ? 'queued' : 'warning_resolved', replayed: false })
      },
    })
    mount('/refresh/failed-run')
    const button = await screen.findByRole('button', { name: action.label })
    expect(screen.getByText('Refresh failed')).toBeInTheDocument()
    fireEvent.click(button)
    expect(calls.filter((call) => call.method !== 'GET')).toHaveLength(0)
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: action.label }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    // Resolving a warning preserves the failed run in history. Its actions
    // disappear after the refreshed response; rerun opens a different run.
    await waitFor(() => expect(screen.queryByRole('button', { name: action.label })).not.toBeInTheDocument())
    await screen.findByText(action.name === 'rerun' ? 'Running' : 'Failed', { exact: true })
    expect(screen.getByRole('heading', { name: action.name === 'rerun' ? 'Run #5' : 'Run #4' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: action.label })).not.toBeInTheDocument()
    const commands = calls.filter((call) => call.method !== 'GET')
    expect(commands).toHaveLength(1)
    expect(commands[0]).toMatchObject({ method: action.method, path: commandPath, body: action.method === 'POST' ? {} : undefined })
    expect(commands[0].headers.get('If-Match')).toBe('"run-7"')
    expect(commands[0].headers.get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/)
    const commandIndex = calls.indexOf(commands[0])
    expect(calls.slice(commandIndex + 1).some((call) => call.method === 'GET' && call.path === `/api/v1/refresh-runs/${action.target}`)).toBe(true)
    expect(calls.slice(commandIndex + 1).some((call) => call.path === '/api/v1/me')).toBe(true)
  })
}

for (const setup of [false, true]) {
  test(`Admin ${setup ? 'setup completes and opens Refresh' : 'opens Schedule and saves all edited values'}`, async () => {
    const admin = { ...me, role: 'admin', landing_screen: setup ? 'setup' : 'waiting', capabilities: [...me.capabilities, 'settings:read', 'settings:write', 'refresh:read'] }
    const settings = { setup_completed_at: setup ? null : publication.published_at, schedule_enabled: true, daily_time: '06:15', timezone: 'America/Merida', revision: '3', updated_at: publication.published_at, updated_by: 'test' }
    const edited = { schedule_enabled: false, daily_time: '08:45', timezone: 'UTC' }
    const { calls } = stubFetch({
      'GET /api/v1/me': json(200, admin),
      'GET /api/v1/settings': json(200, settings, { ETag: '"settings-3"' }),
      'GET /api/v1/settings/schedule-status': [json(200, { next_check_local: '2026-10-05T06:15:00', timezone: settings.timezone, blocker: null }), json(200, { next_check_local: null, blocker: { message: 'Schedule is disabled.' } })],
      'PUT /api/v1/settings': json(200, { ...settings, ...edited, setup_completed_at: publication.published_at, revision: '4' }, { ETag: '"settings-4"' }),
      'GET /api/v1/refresh-runs': json(200, { items: [], actions: [], active_run: null, blocker: null, unresolved_warning: null, next_cursor: null }),
    })
    mount('/')
    if (!setup) fireEvent.click(await screen.findByRole('link', { name: 'Schedule' }))
    await screen.findByRole('heading', { name: setup ? 'Set up Trinity' : 'Schedule' })
    expect(screen.getByRole('switch', { name: 'Schedule enabled' })).toBeChecked()
    expect(screen.getByLabelText('Time', { exact: true })).toHaveValue('06:15')
    expect(screen.getByLabelText('Timezone')).toHaveValue('America/Merida')
    const save = screen.getByRole('button', { name: setup ? 'Complete setup' : 'Save schedule' })
    if (setup) expect(save).toBeEnabled()
    else expect(save).toBeDisabled()
    fireEvent.click(screen.getByRole('switch', { name: 'Schedule enabled' }))
    fireEvent.change(screen.getByLabelText('Time', { exact: true }), { target: { value: edited.daily_time } })
    fireEvent.change(screen.getByLabelText('Timezone'), { target: { value: edited.timezone } })
    expect(save).toBeEnabled()
    fireEvent.click(save)
    if (setup) await screen.findByRole('heading', { name: 'Refresh' })
    else {
      await screen.findByText('Schedule saved.')
      expect(screen.getByRole('switch', { name: 'Schedule enabled' })).not.toBeChecked()
      expect(screen.getByLabelText('Time', { exact: true })).toHaveValue(edited.daily_time)
      expect(screen.getByLabelText('Timezone')).toHaveValue(edited.timezone)
      expect(screen.getByRole('button', { name: 'Save schedule' })).toBeDisabled()
      await screen.findByText('Schedule is disabled.')
    }
    const writes = calls.filter((call) => call.method !== 'GET')
    expect(writes).toHaveLength(1)
    expect(writes[0]).toMatchObject({ method: 'PUT', path: '/api/v1/settings', body: edited })
    expect(writes[0].headers.get('If-Match')).toBe('"settings-3"')
  })
}

for (const role of ['viewer', 'analyst']) {
  for (const path of ['/setup', '/settings']) {
    test(`${role} cannot open ${path} or request settings`, async () => {
      const { calls } = stubFetch({ 'GET /api/v1/me': json(200, { ...me, role, landing_screen: 'waiting', capabilities: role === 'viewer' ? ['national:read'] : me.capabilities }) })
      mount(path)
      await screen.findByRole('heading', { name: 'Nothing to show yet' })
      expect(screen.queryByRole('link', { name: 'Schedule' })).not.toBeInTheDocument()
      expect(screen.queryByRole('switch', { name: 'Schedule enabled' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Save schedule|Complete setup/ })).not.toBeInTheDocument()
      expect(calls.every((call) => call.method === 'GET' && call.path === '/api/v1/me')).toBe(true)
    })
  }
}

test('diagnostics show only warnings that affected rows', () => {
  // A passed warning check has affected_count '0'. Do not show it as a review warning.
  render(<Diagnostics diagnostics={[
    { code: 'D01', severity: 'warning', scope: 'facility', message: 'Facility label is missing.', affected_count: '0' },
    { code: 'D03', severity: 'warning', scope: 'national', message: 'Outage is negative.', affected_count: '2' },
    { code: 'D08', severity: 'info', scope: 'national', message: 'Info only.', affected_count: '11' },
  ]} />)
  expect(screen.queryByText('Facility label is missing.')).not.toBeInTheDocument()
  expect(screen.getByText('Outage is negative.')).toBeInTheDocument()
  expect(screen.queryByText('Info only.')).not.toBeInTheDocument()
})

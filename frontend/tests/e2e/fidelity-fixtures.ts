/**
 * Synthetic API responses for the visual fidelity captures.
 *
 * The values copy the shape of the handoff mock screens so a capture can be
 * compared with its screenshot. They are design examples, not EIA data and
 * not evidence. This file lives under tests/, so it never enters dist/.
 */
import type { Page, Route } from '@playwright/test'

export const PUBLICATION_ID = '5c2e9a71-3f0d-4b6e-9a51-2a7d0c4e8b10'
export const CANDIDATE_ID = '19c0b7d2-6a4e-4f3b-8d21-7e5f9c3a1b64'
export const AWAITING_RUN = '10440f6a-2b7c-4d1e-a9f3-5c8b2e7d4a91'
export const FAILED_RUN = '10380c3d-8e2a-4b5f-91c6-3d7a0e4f2b58'
const PUBLISHED_RUN = '10420b9e-4c1d-4a7f-8e36-9b2d5f1c7a03'
const OLDER_RUN = '10410a2f-7d3e-4c9b-b5a8-1e6c4d2f9b70'
const OLDEST_RUN = '10360e8c-5b4a-4d2f-a7e1-8c3b6d9f0a25'

const publication = {
  publication_event_id: 'b7d14e2a-9c3f-4a6b-8e5d-1f2c3a4b5d6e',
  version_id: PUBLICATION_ID,
  published_at: '2026-09-28T14:10:00Z',
  coverage_start: '2024-09-28',
  coverage_end: '2026-09-27',
  latest_observation_date: '2026-09-27',
}
const freshness = { latest_observation_date: '2026-09-27', published_at: publication.published_at, last_refresh: null }

type Role = 'viewer' | 'analyst' | 'admin'
const CAPABILITIES: Record<Role, string[]> = {
  viewer: ['national:read', 'preview:national'],
  analyst: ['national:read', 'catalog:read', 'preview:national', 'preview:detail', 'sql:execute'],
  admin: ['national:read', 'catalog:read', 'preview:national', 'preview:detail', 'sql:execute', 'settings:read', 'settings:write', 'refresh:read', 'refresh:start', 'refresh:recover', 'candidate:review'],
}

const awaitingSummary = { run_id: AWAITING_RUN, status: 'awaiting_approval', requested_at: '2026-09-29T06:15:00Z', finished_at: null }

export function me(role: Role, published = true) {
  return {
    user_id: role,
    role,
    capabilities: CAPABILITIES[role],
    data_ready: published,
    landing_screen: published ? 'explorer' : 'waiting',
    publication: published ? publication : null,
    admin_context: role === 'admin'
      ? { setup_completed: true, refresh_blocker: null, active_run: published ? awaitingSummary : null, actions: [] }
      : null,
  }
}

/**
 * Build 90 national days that end on 27 Sep 2026.
 *
 * The share is outage ÷ capacity × 100 with two decimals. BigInt keeps the
 * division exact, so the fixture text has the same form as server decimals.
 * Days 4 and 74–76 are gaps: a missing day has null values, never zero.
 */
function nationalDays() {
  const capacity = 100056n
  const days = []
  for (let index = 0; index < 90; index += 1) {
    const period = new Date(Date.UTC(2026, 5, 30 + index)).toISOString().slice(0, 10)
    const gap = index === 4 || (index >= 74 && index <= 76)
    if (gap) {
      days.push({ period, capacity: null, outage: null, percentOutage: null, offline_share_percent: null, reason: 'not_reported' })
      continue
    }
    // A smooth wave around 7.5% with a rise at the end, as in the mock chart.
    const wave = 7600 + 1200 * Math.sin(index / 7) + (index > 76 ? (index - 76) * 420 : 0)
    const outage = index === 89 ? 14420n : index === 88 ? 13438n : BigInt(Math.round(wave))
    // outage × 100 000 ÷ capacity is the share in thousandths of a percent;
    // adding 5 and dividing by 10 rounds it half up to hundredths.
    const hundredths = (outage * 100000n / capacity + 5n) / 10n
    const share = `${hundredths / 100n}.${String(hundredths % 100n).padStart(2, '0')}`
    days.push({ period, capacity: `${capacity}.000`, outage: `${outage}.000`, percentOutage: null, offline_share_percent: share, reason: null })
  }
  return days
}

const FACILITIES: [string, string, string, string][] = [
  ['6008', 'Palo Verde', '1314.000', '3937.000'],
  ['46', 'Browns Ferry', '1160.000', '3480.000'],
  ['649', 'Vogtle', '1117.000', '4536.000'],
  ['6145', 'Comanche Peak', '1205.000', '2430.000'],
  ['880', 'Byron', '0.000', '2347.000'],
]
const facilityColumns = [
  { name: 'period', type: 'date', nullable: false, unit: null },
  { name: 'facility', type: 'string', nullable: false, unit: null },
  { name: 'facilityName', type: 'string', nullable: true, unit: null },
  { name: 'capacity', type: 'decimal', nullable: false, unit: 'MW' },
  { name: 'outage', type: 'decimal', nullable: false, unit: 'MW' },
  { name: 'percentOutage', type: 'decimal', nullable: true, unit: 'percent' },
]
const nationalColumns = [
  { name: 'period', type: 'date', nullable: false, unit: null },
  { name: 'capacity', type: 'decimal', nullable: false, unit: 'MW' },
  { name: 'outage', type: 'decimal', nullable: false, unit: 'MW' },
  { name: 'percentOutage', type: 'decimal', nullable: true, unit: 'percent' },
]
const generatorColumns = [
  { name: 'period', type: 'date', nullable: false, unit: null },
  { name: 'facility', type: 'string', nullable: false, unit: null },
  { name: 'facilityName', type: 'string', nullable: true, unit: null },
  { name: 'generator', type: 'string', nullable: false, unit: null },
  { name: 'capacity', type: 'decimal', nullable: false, unit: 'MW' },
  { name: 'outage', type: 'decimal', nullable: false, unit: 'MW' },
  { name: 'percentOutage', type: 'decimal', nullable: true, unit: 'percent' },
]

const catalog = {
  publication,
  freshness,
  data_ready: true,
  metrics: [{ key: 'offline_share_percent', label: 'Offline share', unit: 'percent', formula: 'outage / capacity * 100', null_reasons: ['not_reported', 'zero_capacity'], display_decimal_places: 2 }],
  datasets: [
    { key: 'national_outages', label: 'National outages', description: 'Whole country, by day.', daily_key: ['period'], columns: nationalColumns, available_filters: ['start', 'end'] },
    { key: 'facility_outages', label: 'Facility outages', description: 'Plant, by day.', daily_key: ['period', 'facility'], columns: facilityColumns, available_filters: ['start', 'end', 'facility'] },
    { key: 'generator_outages', label: 'Generator outages', description: 'Unit, by day.', daily_key: ['period', 'facility', 'generator'], columns: generatorColumns, available_filters: ['start', 'end', 'facility', 'generator'] },
  ],
}

function facilityDayRows(period: string) {
  return FACILITIES.map(([id, name, outage, capacity]) => [period, id, name, capacity, outage, null])
}

function step(stage: string, seq: number, status: string, started: string | null, finished: string | null, error: string | null = null) {
  return { step_id: `step-${stage}-${seq}`, step_seq: String(seq), stage, work_key: stage, attempt: 1, status, started_at: started, finished_at: finished, progress: { processed_count: '3', total_count: '3', unit: 'tasks' }, error_code: error ? 'source_unavailable' : null, error_summary: error }
}

function run(runId: string, seq: string, status: string, steps: unknown[], extra: Record<string, unknown> = {}) {
  return {
    run_id: runId, run_seq: seq, revision: '3', trigger_kind: 'scheduled', requested_by: null, rerun_of_run_id: null,
    requested_at: '2026-09-29T06:15:00Z', started_at: '2026-09-29T06:15:02Z', finished_at: null, status,
    settings_revision: '2', workflow_policy: 'warnings-v1', requested_start: '2024-09-29', requested_end: null,
    candidate: null, warning: null, actions: [], steps, next_steps_cursor: null, poll_after_seconds: null, ...extra,
  }
}

const awaitingRun = run(AWAITING_RUN, '1044', 'awaiting_approval', [
  step('extract', 1, 'succeeded', '2026-09-29T06:15:02Z', '2026-09-29T06:19:14Z'),
  step('prepare', 2, 'succeeded', '2026-09-29T06:19:14Z', '2026-09-29T06:20:19Z'),
  step('validate', 3, 'succeeded', '2026-09-29T06:20:19Z', '2026-09-29T06:20:57Z'),
], { candidate: { version_id: CANDIDATE_ID, review_status: 'required', publication_status: 'not_started' } })

const failedRun = run(FAILED_RUN, '1038', 'failed', [
  step('extract', 1, 'failed', '2026-09-22T06:15:02Z', '2026-09-22T06:16:40Z', 'The EIA source did not respond after three attempts.'),
], {
  requested_at: '2026-09-22T06:15:00Z', finished_at: '2026-09-22T06:16:40Z',
  warning: { warning_id: 'w-1038', run_id: FAILED_RUN, version_id: null, stage: 'extract', code: 'source_unavailable', message: 'The EIA source did not respond after three attempts.', created_at: '2026-09-22T06:16:40Z', resolved_at: null, resolution: null, resolved_by: null },
  actions: [{ action: 'rerun', enabled: true, reason_code: null }, { action: 'delete_warning', enabled: true, reason_code: null }],
})

const candidate = {
  version_id: CANDIDATE_ID, run_id: AWAITING_RUN, revision: '2', validation_status: 'validated', disposition: 'active',
  created_at: '2026-09-29T06:20:19Z', coverage: { start: '2024-09-29', end: '2026-09-28' }, latest_observation_date: '2026-09-28',
  manifest_sha256: null,
  validation: { status: 'passed', step_id: 'step-validate-3', checkset: 'trinity-data-v1', expected_required_count: 16, passed_required_count: 16, checks: [] },
  diagnostics: [{ code: 'share_out_of_range', severity: 'warning', scope: 'national', message: 'On 12 Sep the offline share is 102.40. That is outside 0–100, and it was left as-is.', affected_count: '1' }],
  review_warning_count: '1', review_warning_digest: null, review_status: 'required', approval_required: true, approval: null,
  publication: { status: 'not_started', generation: '0', attempt: 0, error_code: null, error_summary: null, published_at: null, publication_event_id: null },
  failure_warning: null, discarded_at: null, discarded_by: null,
  actions: [{ action: 'approve', enabled: true, reason_code: null }, { action: 'publication_retry', enabled: false, reason_code: 'not_applicable' }, { action: 'discard', enabled: true, reason_code: null }],
}

const runList = {
  items: [
    awaitingSummary,
    { run_id: PUBLISHED_RUN, status: 'succeeded', requested_at: '2026-09-28T14:02:00Z', finished_at: '2026-09-28T14:10:00Z' },
    { run_id: OLDER_RUN, status: 'succeeded', requested_at: '2026-09-27T06:15:00Z', finished_at: '2026-09-27T06:22:00Z' },
    { run_id: FAILED_RUN, status: 'failed', requested_at: '2026-09-22T06:15:00Z', finished_at: '2026-09-22T06:16:40Z' },
    { run_id: OLDEST_RUN, status: 'succeeded', requested_at: '2026-09-20T06:15:00Z', finished_at: '2026-09-20T06:21:00Z' },
  ],
  next_cursor: null,
  active_run: awaitingSummary,
  unresolved_warning: null,
  blocker: null,
  actions: [{ action: 'start_refresh', enabled: false, reason_code: 'review_required' }],
}

const settings = { setup_completed_at: '2026-09-01T12:00:00Z', schedule_enabled: true, daily_time: '06:15', timezone: 'America/New_York', revision: '2', updated_at: '2026-09-01T12:00:00Z', updated_by: 'admin' }
const scheduleStatus = { settings_revision: '2', schedule_enabled: true, next_check_at: '2026-09-30T10:15:00Z', next_check_local: '2026-09-30T06:15:00-04:00', timezone: 'America/New_York', evaluated_at: '2026-09-29T12:00:00Z', eligible_now: false, blocker: null }

function problem(status: number, code: string) {
  return { type: 'about:blank', title: 'Bad Request', status, detail: 'Bad Request', code, request_id: 'req-fidelity', errors: [], blocker: null, current_revision: null }
}

/** Options for one capture: the role, the publication state and any SQL failure. */
export type Scenario = { role: Role; published?: boolean; sqlError?: boolean; sqlEmpty?: boolean; refreshBlocked?: boolean }

/**
 * Answer every /api/v1 request with the synthetic data above.
 * An unknown path gets a 404 problem, so a missing fixture is visible.
 */
export async function routeApi(page: Page, scenario: Scenario) {
  const published = scenario.published ?? true
  await page.route('**/api/v1/**', async (route: Route) => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace('/api/v1', '')
    const json = (body: unknown, headers: Record<string, string> = {}) => route.fulfill({ json: body, headers })
    if (path === '/me') return json(me(scenario.role, published))
    if (path === '/auth/login') return route.fulfill({ status: 401, json: problem(401, 'invalid_credentials') })
    if (!published && path !== '/refresh-runs' && path !== '/settings') return route.fulfill({ status: 409, json: problem(409, 'data_unavailable') })
    if (path === '/dashboard/national') {
      const days = nationalDays()
      return json({ publication, range: { start: days[0].period, end: days.at(-1)!.period }, summary: days.at(-1), days, diagnostics: [], freshness })
    }
    if (path === '/metrics/offline-share') return json({ publication, period: url.searchParams.get('period'), metric: { value: '13.43', reason: null }, diagnostics: [] })
    if (path === '/catalog') return json(catalog)
    if (path === '/datasets/facility_outages/preview') {
      const facility = url.searchParams.get('facility')
      const start = url.searchParams.get('start') ?? '2026-09-20'
      const end = url.searchParams.get('end') ?? '2026-09-27'
      const rows = facility
        ? Array.from({ length: 8 }, (_, i) => new Date(Date.UTC(2026, 8, 20 + i)).toISOString().slice(0, 10))
          .filter((d) => d >= start && d <= end && d !== '2026-09-23')
          .map((d, i) => [d, facility, FACILITIES.find((f) => f[0] === facility)?.[1] ?? null, '3480.000', i % 3 === 0 ? '0.000' : '1160.000', null])
        : start === end ? facilityDayRows(start) : facilityDayRows('2026-09-27')
      return json({ publication, dataset_key: 'facility_outages', range: { start, end }, columns: facilityColumns, rows, returned_rows: rows.length, next_cursor: null, reason: null, diagnostics: [] })
    }
    if (path === '/datasets/national_outages/preview') {
      const rows = nationalDays().slice(-8).map((d) => [d.period, d.capacity, d.outage, null])
      return json({ publication, dataset_key: 'national_outages', range: { start: '2026-09-20', end: '2026-09-27' }, columns: nationalColumns, rows, returned_rows: rows.length, next_cursor: null, reason: null, diagnostics: [] })
    }
    if (path === '/datasets/generator_outages/preview') {
      const rows = [['2026-09-27', '46', 'Browns Ferry', '1', '1160.000', '1160.000', null], ['2026-09-27', '46', 'Browns Ferry', '2', '1160.000', '0.000', null], ['2026-09-27', '46', 'Browns Ferry', '3', '1160.000', '0.000', null]]
      return json({ publication, dataset_key: 'generator_outages', range: { start: '2026-09-27', end: '2026-09-27' }, columns: generatorColumns, rows, returned_rows: rows.length, next_cursor: null, reason: null, diagnostics: [] })
    }
    if (path.endsWith('/facilities')) return json({ publication, range: { start: '2026-09-20', end: '2026-09-27' }, items: FACILITIES.map(([facility, facilityName]) => ({ facility, facilityName })), next_cursor: null })
    if (path.endsWith('/generators')) return json({ publication, range: { start: '2026-09-20', end: '2026-09-27' }, facility: '46', items: ['1', '2', '3'].map((generator) => ({ facility: '46', generator })), next_cursor: null })
    if (path === '/queries') {
      if (scenario.sqlError) return route.fulfill({ status: 400, json: problem(400, 'sql_not_allowed') })
      if (scenario.sqlEmpty) return json({ publication, columns: facilityColumns.slice(0, 2), rows: [], returned_rows: 0, truncated: false, execution_ms: 21, diagnostics: [] })
      const rows = [['2026-09-20', 'Browns Ferry', '3480.000', '0.000'], ['2026-09-21', 'Browns Ferry', '3480.000', null], ['2026-09-26', 'Browns Ferry', '3480.000', '1160.000'], ['2026-09-27', 'Browns Ferry', '3480.000', '1160.000']]
      return json({ publication, columns: [facilityColumns[0], facilityColumns[2], facilityColumns[3], { ...facilityColumns[4], nullable: true }], rows, returned_rows: rows.length, truncated: false, execution_ms: 143, diagnostics: [] })
    }
 if (path === '/refresh-runs' && scenario.refreshBlocked) {
      return json({ ...runList, active_run: null, items: runList.items.slice(1), actions: [{ action: 'start_refresh', enabled: false, reason_code: 'failure_unresolved' }],
        blocker: { code: 'failure_unresolved', message: 'The last run failed at Retrieve. Run it again or resolve its warning before a new refresh.', run_id: FAILED_RUN, version_id: null, warning_id: 'w-1038' },
        unresolved_warning: failedRun.warning })
    }
    if (path === '/refresh-runs') return json(published ? runList : { ...runList, items: [], active_run: null, actions: [{ action: 'start_refresh', enabled: true, reason_code: null }] })
    if (path === `/refresh-runs/${AWAITING_RUN}`) return json(awaitingRun, { ETag: '"3"' })
    if (path === `/refresh-runs/${FAILED_RUN}`) return json(failedRun, { ETag: '"3"' })
    if (path === `/candidates/${CANDIDATE_ID}`) return json(candidate, { ETag: '"2"' })
    if (path === '/settings') return json(settings, { ETag: '"2"' })
    if (path === '/settings/schedule-status') return json(scheduleStatus)
    return route.fulfill({ status: 404, json: problem(404, 'resource_not_found') })
  })
}

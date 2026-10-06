/** Measure complete authenticated HTTP reads without recording credentials or bodies.
 * Supply the three TRINITY_TEST_<ROLE>_PASSWORD environment values at invocation.
 * Each test session is revoked in finally. No refresh/settings/publication command runs.
 */
import { createHash } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import { parseArgs } from 'node:util'

const { values } = parseArgs({ options: {
  phase: { type: 'string', default: 'after' },
  output: { type: 'string' },
  'compare-to': { type: 'string' },
  'base-url': { type: 'string', default: 'http://127.0.0.1:8000' },
} })
const base = new URL(values['base-url'])
if (!['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname) || base.username || base.password
    || base.search || base.hash || base.pathname !== '/' || !['http:', 'https:'].includes(base.protocol)) {
  throw new Error('Use a loopback API origin')
}
if (!['before', 'after'].includes(values.phase)) throw new Error('Use phase before or after')

const roles = ['viewer', 'analyst', 'admin']
const tokens = new Map()
const report = { phase: values.phase, started_at: new Date().toISOString(), publication: null,
  requests: [], checks: {}, logout: [], summary: [], ok: false }
let expectedWarmSince = null

class ProbeFailure extends Error {}
const fail = (label) => { throw new ProbeFailure(label) }
const rounded = (value) => Math.round(value * 100) / 100
const digest = (value) => createHash('sha256').update(JSON.stringify(value)).digest('hex')

async function send(role, path, { method = 'GET', body } = {}) {
  const headers = { Accept: 'application/json' }
  if (tokens.has(role)) headers.Authorization = `Bearer ${tokens.get(role)}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  return fetch(new URL(path, base), { method, headers, body: body === undefined ? undefined : JSON.stringify(body),
    redirect: 'error', cache: 'no-store', signal: AbortSignal.timeout(45000) })
}

async function measure(role, path, label, expectedStatus = 200) {
  const started = performance.now(), startedAt = new Date().toISOString()
  const response = await send(role, path)
  const raw = await response.arrayBuffer()
  const elapsed = performance.now() - started
  const data = JSON.parse(new TextDecoder().decode(raw))
  const sample = { role, path, label, started_at: startedAt, status: response.status,
    ms: rounded(elapsed), bytes: raw.byteLength, no_store: response.headers.get('cache-control') === 'no-store',
    within_initial_58s_window: expectedWarmSince === null ? null : started - expectedWarmSince < 58000 }
  if (data.code && response.status !== 200) sample.error_code = data.code
  report.requests.push(sample)
  console.log(JSON.stringify(sample))
  if (response.status !== expectedStatus) fail(`Unexpected status for ${role} ${path}`)
  if (!sample.no_store) fail('Authenticated read lacked no-store')
  if (response.status !== 200) return data
  if (!data.publication) fail('Expected an active publication')
  report.publication ??= data.publication
  if (JSON.stringify(report.publication) !== JSON.stringify(data.publication)) fail('Publication changed during measurement')
  if (path.startsWith('/api/v1/dashboard/national')) {
    const preset = new URL(path, base).searchParams.get('preset')
    const count = { '30d': 30, '90d': 90, '1y': 365 }[preset]
    if (data.days?.length !== count || data.range?.end !== data.summary?.period
        || data.summary?.period !== report.publication.latest_observation_date) fail('Dashboard range or summary mismatch')
    sample.days = data.days.length
    sample.data_digest = digest({ range: data.range, days: data.days, summary: data.summary, diagnostics: data.diagnostics })
  } else if (path.includes('/preview')) {
    if (data.next_cursor !== null || data.returned_rows !== data.rows?.length) fail('Preview was incomplete')
    sample.rows = data.returned_rows
    sample.data_digest = digest({ range: data.range, columns: data.columns, rows: data.rows, diagnostics: data.diagnostics })
  }
  return data
}

async function loginAll() {
  for (const role of roles) {
    const password = process.env[`TRINITY_TEST_${role.toUpperCase()}_PASSWORD`]
    if (!password) fail(`Missing configured ${role} password`)
    const response = await send(role, '/api/v1/auth/login', { method: 'POST', body: { username: role, password } })
    if (response.status !== 200) fail(`Login failed for ${role}`)
    const body = await response.json()
    if (typeof body.access_token !== 'string') fail('Login returned no session')
    tokens.set(role, body.access_token)
    const me = await measure(role, '/api/v1/me', 'identity_control')
    if (me.role !== role || !me.data_ready) fail('Persona or publication readiness mismatch')
  }
}

async function logoutAll() {
  for (const role of roles) {
    if (!tokens.has(role)) continue
    try {
      const ended = await send(role, '/api/v1/auth/logout', { method: 'POST', body: {} })
      const denied = await send(role, '/api/v1/me')
      report.logout.push({ role, status: ended.status, revoked: denied.status === 401 })
      if (ended.status !== 204 || denied.status !== 401) report.ok = false
    } catch {
      report.logout.push({ role, revoked: false })
      report.ok = false
    } finally { tokens.delete(role) }
  }
}

function summarize() {
  const groups = new Map()
  for (const sample of report.requests.filter((item) => item.status === 200)) {
    const key = `${sample.role} ${sample.path} ${sample.label}`
    const group = groups.get(key) ?? []
    group.push(sample.ms)
    groups.set(key, group)
  }
  for (const [key, durations] of groups) {
    durations.sort((a, b) => a - b)
    const middle = Math.floor(durations.length / 2)
    const median = durations.length % 2 ? durations[middle] : (durations[middle - 1] + durations[middle]) / 2
    report.summary.push({ group: key, samples: durations.length, min_ms: durations[0],
      median_ms: rounded(median), max_ms: durations.at(-1) })
  }
}

async function main() {
  try {
    await loginAll()
    const national = '/api/v1/dashboard/national?preset=30d'
    const day = report.publication.latest_observation_date
    const facility = `/api/v1/datasets/facility_outages/preview?start=${day}&end=${day}&limit=1000`
    if (values.phase === 'before') {
      for (let sample = 0; sample < 3; sample++) await measure('viewer', national, 'uncached_api')
      await measure('viewer', '/api/v1/dashboard/national?preset=1y', 'uncached_api')
      await measure('analyst', national, 'uncached_api')
      await measure('analyst', facility, 'uncached_api')
      await measure('admin', national, 'uncached_api')
    } else {
      expectedWarmSince = performance.now()
      await measure('viewer', national, 'first_after_rebuild_expected_cold')
      for (let sample = 0; sample < 2; sample++) await measure('viewer', national, 'expected_warm')
      await measure('viewer', '/api/v1/dashboard/national?preset=90d', 'expected_warm')
      await measure('viewer', '/api/v1/dashboard/national?preset=1y', 'expected_warm')
      for (let sample = 0; sample < 2; sample++) await measure('analyst', national, 'expected_warm')
      for (let sample = 0; sample < 2; sample++) await measure('analyst', facility, 'expected_warm')
      for (let sample = 0; sample < 2; sample++) await measure('admin', national, 'expected_warm')
      await measure('viewer', facility, 'warm_cache_permission_denial', 404)

      console.log(JSON.stringify({ waiting_seconds: 65, reason: 'allow fixed evidence TTL to expire' }))
      await new Promise((resolve) => setTimeout(resolve, 65000))
      expectedWarmSince = performance.now()
      await Promise.all([
        measure('analyst', national, 'concurrent_after_expiry_expected_cold'),
        measure('analyst', facility, 'concurrent_after_expiry_expected_cold'),
      ])
      await measure('viewer', national, 'warm_after_concurrent_fill')
      await measure('admin', national, 'warm_after_concurrent_fill')
      report.checks.viewer_detail_denied = true
    }
    const byPath = new Map()
    for (const sample of report.requests.filter((item) => item.data_digest)) {
      if (byPath.has(sample.path) && byPath.get(sample.path) !== sample.data_digest) fail('Data differed for identical reads')
      byPath.set(sample.path, sample.data_digest)
    }
    report.checks.identical_repeated_data = true
    if (values['compare-to']) {
      const before = JSON.parse(readFileSync(values['compare-to'], 'utf8'))
      if (!before.ok || JSON.stringify(before.publication) !== JSON.stringify(report.publication)) fail('Baseline publication mismatch')
      for (const sample of before.requests.filter((item) => item.data_digest)) {
        if (byPath.has(sample.path) && byPath.get(sample.path) !== sample.data_digest) fail('Before/after data mismatch')
      }
      report.checks.baseline_publication_and_data_match = true
    }
    report.ok = true
  } catch (error) {
    report.failure = error instanceof ProbeFailure ? error.message : 'Transport or measurement failure'
  } finally {
    await logoutAll()
    report.finished_at = new Date().toISOString()
    summarize()
    if (values.output) writeFileSync(values.output, JSON.stringify(report, null, 2) + '\n')
    console.log(JSON.stringify({ ok: report.ok, failure: report.failure, checks: report.checks,
      logout: report.logout, summary: report.summary }))
    if (!report.ok) process.exitCode = 1
  }
}

await main()

/** Measure sign-in-to-dashboard milestones in fresh Chromium contexts.
 * Passwords arrive through TRINITY_TEST_<ROLE>_PASSWORD. No traces, screenshots,
 * request headers or response bodies are saved. Revoke each new test session.
 */
import { createRequire } from 'node:module'
import { writeFileSync } from 'node:fs'
import { parseArgs } from 'node:util'

const require = createRequire(new URL('../frontend/package.json', import.meta.url))
const { chromium } = require('@playwright/test')
const { values } = parseArgs({ options: { output: { type: 'string' }, role: { type: 'string' },
  'desktop-only': { type: 'boolean', default: false } } })
if (values.role && !['viewer', 'analyst', 'admin'].includes(values.role)) throw new Error('Unknown persona')
const base = 'http://127.0.0.1:5173'
const api = 'http://127.0.0.1:8000'
const rounded = (value) => Math.round(value * 100) / 100
const report = { started_at: new Date().toISOString(), samples: [], ok: true }
const browser = await chromium.launch({ headless: true })

try {
  for (const [role, width, height] of [
    ['viewer', 1440, 1000], ['analyst', 1440, 1000], ['admin', 1440, 1000],
    ['viewer', 390, 844], ['analyst', 390, 844],
  ]) {
    if (values.role && values.role !== role || values['desktop-only'] && width !== 1440) continue
    const context = await browser.newContext({ viewport: { width, height } })
    const page = await context.newPage()
    const sample = { role, viewport: `${width}x${height}`, requests: [], failed_requests: 0, failures: [], page_errors: 0 }
    const pending = []
    let token = null
    let start = null
    page.on('pageerror', () => { sample.page_errors++ })
    page.on('requestfailed', (request) => {
      const url = new URL(request.url())
      if (!url.pathname.startsWith('/api/v1/')) return
      sample.failed_requests++
      sample.failures.push({ path: url.pathname, kind: request.failure()?.errorText.includes('ABORTED') ? 'aborted' : 'transport_failure' })
    })
    page.on('requestfinished', (request) => {
      const url = new URL(request.url())
      if (!url.pathname.startsWith('/api/v1/')) return
      pending.push((async () => {
        const response = await request.response()
        sample.requests.push({ path: url.pathname + url.search, status: response?.status(),
          ms: rounded(request.timing().responseEnd),
          finished_after_click_ms: start === null ? null : rounded(performance.now() - start) })
      })())
    })
    try {
      await page.goto(`${base}/sign-in`)
      await page.getByLabel('Account', { exact: true }).fill(role)
      const password = process.env[`TRINITY_TEST_${role.toUpperCase()}_PASSWORD`]
      if (!password) throw new Error('Credential unavailable')
      await page.getByLabel('Password', { exact: true }).fill(password)
      const loginPromise = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/auth/login', { timeout: 45000 })
      const dashboardPromise = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/dashboard/national'
        && response.status() === 200, { timeout: 45000 })
      // Keep a failure of either pending response from becoming an unhandled
      // rejection while the UI assertion records a safe failure below.
      void dashboardPromise.catch(() => {})
      void loginPromise.catch(() => {})
      start = performance.now()
      sample.clicked_at = new Date().toISOString()
      await page.getByRole('button', { name: 'Sign in', exact: true }).click()
      const loggedIn = await loginPromise
      if (loggedIn.status() !== 200) throw new Error('Login failed')
      token = (await loggedIn.json()).access_token
      await page.getByRole('heading', { name: /^Range end observation/ }).waitFor({ timeout: 45000 })
      await page.getByRole('application', { name: /^National offline share/ }).waitFor({ timeout: 45000 })
      sample.cards_and_chart_rendered_ms = rounded(performance.now() - start)
      const data = await (await dashboardPromise).json()
      if (typeof data.summary.offline_share_percent === 'string') {
        // The API supplies the two-decimal percentage. Wait for the animated
        // counter to show that value rather than counting its initial zero.
        await page.waitForFunction((expected) => document.querySelector('.hero-value')?.textContent?.includes(expected),
          `${data.summary.offline_share_percent}%`, { timeout: 10000 })
      }
      sample.cards_settled_ms = rounded(performance.now() - start)
      if (role !== 'viewer') {
        await page.getByRole('heading', { name: /^Reported facility contributions/ }).waitFor({ timeout: 45000 })
        sample.facility_list_rendered_ms = rounded(performance.now() - start)
      }
      await Promise.all(pending)
      sample.publication_event_id = data.publication.publication_event_id
      sample.summary_period = data.summary.period
      sample.detail_request_count = sample.requests.filter((request) => request.path.includes('facility_outages')
        || request.path.includes('generator_outages')).length
      sample.ok = sample.page_errors === 0 && sample.requests.every((request) => request.status < 400)
        && (role !== 'viewer' || sample.detail_request_count === 0)
    } catch {
      sample.ok = false
      sample.failure = 'Browser login, rendering or timing check failed'
      try {
        sample.failure_state = { route: new URL(page.url()).pathname,
          dashboard_headings: await page.getByRole('heading', { name: /^Range end observation/ }).count(),
          facility_headings: await page.getByRole('heading', { name: /^Reported facility contributions/ }).count(),
          retry_buttons: await page.getByRole('button', { name: /Retry|Restart|Reload/ }).count(),
          busy_regions: await page.locator('[aria-busy="true"]').count() }
      } catch { sample.failure_state = 'Page unavailable' }
    } finally {
      if (token) {
        try {
          const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
          const ended = await fetch(`${api}/api/v1/auth/logout`, { method: 'POST', headers, body: '{}', signal: AbortSignal.timeout(10000) })
          const denied = await fetch(`${api}/api/v1/me`, { headers, signal: AbortSignal.timeout(10000) })
          sample.session_revoked = ended.status === 204 && denied.status === 401
        } catch { sample.session_revoked = false }
        token = null
      }
      await context.close()
      if (!sample.ok || !sample.session_revoked) report.ok = false
      report.samples.push(sample)
      console.log(JSON.stringify(sample))
    }
  }
} finally {
  await browser.close()
  report.finished_at = new Date().toISOString()
  if (values.output) writeFileSync(values.output, JSON.stringify(report, null, 2) + '\n')
  console.log(JSON.stringify({ ok: report.ok, samples: report.samples.length }))
  if (!report.ok) process.exitCode = 1
}

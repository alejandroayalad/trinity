/** Presentation checks use synthetic API responses, never retained mutations. */
import { expect, test } from '@playwright/test'

const publication = { publication_event_id: 'synthetic-event', version_id: 'synthetic-version', published_at: '2026-10-06T00:00:00Z', coverage_start: '2026-10-01', coverage_end: '2026-10-05', latest_observation_date: '2026-10-05' }
const day = { period: '2026-10-05', capacity: '100', outage: '120', percentOutage: null, offline_share_percent: '120.00', reason: null }
const freshness = { latest_observation_date: day.period, published_at: publication.published_at, last_refresh: null }

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem('trinity.session', JSON.stringify({ access_token: 'synthetic-test-only', expires_at: '2099-01-01T00:00:00Z' })))
  await page.emulateMedia({ reducedMotion: 'reduce' })
})

test('mobile and desktop chart labels retain readable size without clipping', async ({ page }, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.route('**/api/v1/**', (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/me')) return route.fulfill({ json: { user_id: 'synthetic', role: 'viewer', capabilities: ['national:read'], data_ready: true, landing_screen: 'explorer', publication, admin_context: null } })
    expect(path).toBe('/api/v1/dashboard/national')
    return route.fulfill({ json: { publication, range: { start: '2026-10-03', end: day.period }, summary: day, days: [{ ...day, period: '2026-10-03', outage: null, offline_share_percent: null, reason: 'not_reported' }, { ...day, period: '2026-10-04', outage: '-5', offline_share_percent: '-5.00' }, day], diagnostics: [], freshness } })
  })
  await page.goto('/dashboard')
  const chart = page.getByRole('application')
  await expect(chart).toBeVisible()
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    await expect.poll(async () => chart.evaluate((svg) => Math.abs(svg.getBoundingClientRect().width - (svg as SVGSVGElement).viewBox.baseVal.width))).toBeLessThan(1)
    const layout = await chart.evaluate((svg) => {
      const bounds = svg.getBoundingClientRect()
      return [...svg.querySelectorAll('text')].map((text) => {
        const box = text.getBoundingClientRect()
        return { label: text.textContent, height: box.height, left: box.left - bounds.left, right: box.right - bounds.left, width: bounds.width }
      })
    })
    expect(layout.every((label) => label.height >= 13)).toBe(true)
    expect(layout.every((label) => label.left >= 0 && label.right <= label.width)).toBe(true)
    const dates = layout.filter((label) => label.label?.startsWith('2026-'))
    expect(dates[0].right).toBeLessThan(dates[1].left)
    await testInfo.attach(`labels-${width}`, { body: JSON.stringify(layout), contentType: 'application/json' })
    await chart.screenshot({ path: testInfo.outputPath(`chart-${width}.png`) })
  }
  await chart.focus(); await page.keyboard.press('ArrowRight'); await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: 'Selected observation · 2026-10-04' })).toBeVisible()
  expect(errors).toEqual([])
})

test('duplicate SQL headers retain both columns without console key warnings', async ({ page }) => {
  const errors: string[] = []
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
  const columns = [{ name: 'value', type: 'decimal', nullable: false, unit: 'MW' }, { name: 'value', type: 'decimal', nullable: false, unit: 'MW' }]
  await page.route('**/api/v1/**', (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/me')) return route.fulfill({ json: { user_id: 'synthetic', role: 'analyst', capabilities: ['national:read', 'catalog:read', 'sql:execute'], data_ready: true, landing_screen: 'explorer', publication, admin_context: null } })
    if (path.endsWith('/catalog')) return route.fulfill({ json: { publication, datasets: [], metrics: [], data_ready: true, freshness } })
    expect(path).toBe('/api/v1/queries')
    return route.fulfill({ json: { publication, columns, rows: [['1.00', '2.00']], returned_rows: 1, truncated: false, execution_ms: 1, diagnostics: [] } })
  })
  await page.goto('/sql')
  await page.getByRole('button', { name: 'Run query', exact: true }).click()
  await expect(page.getByRole('columnheader', { name: 'value (MW)', exact: true })).toHaveCount(2)
  await expect(page.getByRole('cell', { name: '1.00', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: '2.00', exact: true })).toBeVisible()
  expect(errors).toEqual([])
})

test('a published candidate reports success without requesting approval or sending mutations', async ({ page }, testInfo) => {
  const methods: string[] = []
  await page.route('**/api/v1/**', (route) => {
    methods.push(route.request().method())
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/me')) return route.fulfill({ json: { user_id: 'synthetic', role: 'admin', capabilities: ['national:read', 'refresh:read', 'candidate:review'], data_ready: true, landing_screen: 'explorer', publication, admin_context: null } })
    if (path.endsWith('/refresh-runs/run')) return route.fulfill({ json: { run_id: 'run', run_seq: '1', revision: '1', requested_at: publication.published_at, status: 'succeeded', candidate: { version_id: 'candidate' }, warning: null, actions: [], steps: [], next_steps_cursor: null, poll_after_seconds: null } })
    expect(path).toBe('/api/v1/candidates/candidate')
    return route.fulfill({ json: { version_id: 'candidate', disposition: 'active', validation_status: 'validated', validation: { passed_required_count: 16, expected_required_count: 16 }, diagnostics: [], review_status: 'not_required', publication: { status: 'published' }, actions: [] } })
  })
  await page.goto('/refresh/run')
  await expect(page.getByText('This candidate was published successfully.', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Approve', exact: true })).toHaveCount(0)
  expect(methods.every((method) => method === 'GET')).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('published-candidate.png') })
})

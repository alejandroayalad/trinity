/** Simulated transport failures and data. This does not measure backend capacity. */
import { expect, test } from '@playwright/test'

const publication = { publication_event_id: 'synthetic-event', version_id: 'synthetic-version', published_at: '2026-10-06T00:00:00Z', coverage_start: '2026-10-01', coverage_end: '2026-10-05', latest_observation_date: '2026-10-05' }
const summary = { period: '2026-10-05', capacity: '100', outage: '10', percentOutage: '10', offline_share_percent: '10.00', reason: null }
const dashboard = { publication, range: { start: '2026-10-01', end: '2026-10-05' }, days: [{ ...summary, period: '2026-10-04' }, summary], summary, diagnostics: [], freshness: { latest_observation_date: summary.period, published_at: publication.published_at, last_refresh: null } }

test.beforeEach(async ({ page }) => {
  // The token is a synthetic sentinel; every API call is intercepted.
  await page.addInitScript(() => sessionStorage.setItem('trinity.session', JSON.stringify({ access_token: 'synthetic-test-only', expires_at: '2099-01-01T00:00:00Z' })))
})

test('simulated dashboard: rapid cancellation, accessible updating, bounded 429 and manual recovery', async ({ page }, testInfo) => {
  const requests: string[] = [], cancelled: string[] = [], statuses: number[] = [], errors: string[] = []
  let releaseOld!: () => void
  const old = new Promise<void>((resolve) => { releaseOld = resolve })
  let phase: 'success' | 'failure' | 'recovery' = 'success'
  page.on('requestfailed', (request) => { if (request.url().includes('/dashboard/national')) cancelled.push(new URL(request.url()).search) })
  page.on('console', (message) => { if (message.type() === 'error' && !message.text().includes('status of 429')) errors.push(message.text()) })
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/me')) return route.fulfill({ json: { user_id: 'synthetic', role: 'viewer', capabilities: ['national:read'], data_ready: true, landing_screen: 'explorer', publication, admin_context: null } })
    expect(url.pathname).toBe('/api/v1/dashboard/national')
    requests.push(url.search)
    if (url.searchParams.get('preset') === '1y') { await old; return route.fulfill({ json: dashboard }) }
    if (phase === 'failure') { statuses.push(429); return route.fulfill({ status: 429, headers: { 'Retry-After': '0' }, json: { code: 'rate_limited' } }) }
    statuses.push(200)
    return route.fulfill({ json: dashboard })
  })
  await page.goto('/dashboard')
  await expect(page.getByText('Selected range loaded.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Last 365 days', exact: true }).click()
  await expect(page.getByText(/Showing previous data/)).toHaveAttribute('role', 'status')
  phase = 'failure'
  await page.getByRole('button', { name: '90 days', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Retry', exact: true })).toBeVisible()
  expect(requests.filter((q) => q.includes('90d'))).toHaveLength(2)
  phase = 'recovery'
  await page.getByRole('button', { name: 'Retry', exact: true }).dblclick()
  await expect(page.getByText('Selected range loaded.', { exact: true })).toBeVisible()
  releaseOld()
  await expect.poll(() => cancelled.length).toBeGreaterThan(0)
  expect(requests.filter((q) => q.includes('90d'))).toHaveLength(3)
  expect(statuses.filter((s) => s === 429)).toHaveLength(2)
  expect(errors).toEqual([])
  await page.screenshot({ path: testInfo.outputPath('dashboard-recovered.png') })
  await testInfo.attach('simulated-network-counts', { body: JSON.stringify({ requests, cancelled, statuses, consoleErrors: errors.length }), contentType: 'application/json' })
})

test('simulated catalog: debounce, prefiltered exact IDs, cached pagination revisit and Reset', async ({ page }, testInfo) => {
  const reads: { path: string; search: string }[] = []
  const columns = [{ name: 'period', type: 'date', nullable: false, unit: null }, { name: 'capacity', type: 'decimal', nullable: false, unit: 'MW' }, { name: 'outage', type: 'decimal', nullable: false, unit: 'MW' }]
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/me')) return route.fulfill({ json: { user_id: 'synthetic', role: 'analyst', capabilities: ['national:read', 'catalog:read', 'preview:detail'], data_ready: true, landing_screen: 'explorer', publication, admin_context: null } })
    if (url.pathname.endsWith('/catalog')) return route.fulfill({ json: { publication, datasets: [], metrics: [], data_ready: true, freshness: dashboard.freshness } })
    reads.push({ path: url.pathname, search: url.search })
    if (url.pathname.endsWith('/facilities')) return route.fulfill({ json: { publication, items: [{ facility: '0001', facilityName: 'Synthetic plant' }], next_cursor: null } })
    if (url.pathname.endsWith('/generators')) return route.fulfill({ json: { publication, items: [{ facility: '0001', generator: '01' }], next_cursor: null } })
    expect(url.pathname).toBe('/api/v1/datasets/generator_outages/preview')
    return route.fulfill({ json: { publication, dataset_key: 'generator_outages', range: dashboard.range, columns, rows: [[summary.period, '100', '10']], returned_rows: 1, next_cursor: url.searchParams.has('cursor') ? null : 'second', reason: null, diagnostics: [] } })
  })
  await page.goto('/catalog/generator_outages?facility=0001&generator=01')
  await expect(page.getByText(/Showing 1 rows/)).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Facility', exact: true })).toHaveValue('0001')
  await expect(page.getByRole('combobox', { name: 'Generator', exact: true })).toHaveValue('01')
  expect(reads.some((r) => r.path.endsWith('/generators'))).toBe(false)
  await page.getByRole('button', { name: 'Load more', exact: true }).click()
  await expect(page.getByText('2 rows', { exact: true })).toBeVisible()
  await expect(page.getByText(/^Combined offline share for these rows:/)).toBeVisible()
  await page.getByLabel('From', { exact: true }).fill('2026-10-01')
  await page.getByRole('button', { name: 'Apply dates', exact: true }).click()
  await expect(page.getByText(/Showing 1 rows/)).toBeVisible()
  await page.getByLabel('From', { exact: true }).fill('')
  await page.getByRole('button', { name: 'Apply dates', exact: true }).click()
  await expect(page.getByText(/Showing 1 rows/)).toBeVisible()
  const previews = reads.filter((r) => r.path.endsWith('/preview'))
  expect(previews.filter((r) => r.search.includes('cursor'))).toHaveLength(1)
  await page.getByLabel('Search facilities').pressSequentially('Synthetic')
  await expect(page.getByRole('option', { name: 'Synthetic plant (0001)' })).toBeAttached()
  const terms = reads.filter((r) => r.path.endsWith('/facilities')).map((r) => new URLSearchParams(r.search).get('search')).filter(Boolean)
  expect(terms).toEqual(['Synthetic'])
  await page.getByLabel('Search facilities').fill('obsolete')
  await page.getByRole('button', { name: 'Reset filters', exact: true }).click()
  await expect(page.getByLabel('Search facilities')).toHaveValue('')
  await expect(page.getByRole('combobox', { name: 'Facility', exact: true })).toHaveValue('')
  await expect(page.getByRole('combobox', { name: 'Generator', exact: true })).toHaveValue('')
  await expect(page.getByText(/Showing 1 rows/)).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('catalog-reset.png') })
  await testInfo.attach('simulated-network-counts', { body: JSON.stringify(reads), contentType: 'application/json' })
})

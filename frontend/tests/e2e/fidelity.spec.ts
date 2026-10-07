/**
 * Capture every handoff screen at 1440px and 924px with synthetic data.
 *
 * Each test opens one screen in the state of its handoff screenshot and saves
 * a full-page PNG named after that screenshot, for example
 * `13-run-review-1440.png`. The captures support the side-by-side review in
 * sdd/ui-fidelity/acceptance.md. They do not assert visual equality.
 *
 * The tests wait for loading to end through `aria-busy`, not for copy, so the
 * same file runs before and after the copy changes.
 */
import { expect, test, type Page } from '@playwright/test'
import { AWAITING_RUN, FAILED_RUN, routeApi, type Scenario } from './fidelity-fixtures'

const WIDTHS = [1440, 924] as const

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
})

async function signedIn(page: Page, scenario: Scenario) {
  await page.addInitScript(() => sessionStorage.setItem('trinity.session', JSON.stringify({ access_token: 'synthetic-test-only', expires_at: '2099-01-01T00:00:00Z' })))
  await routeApi(page, scenario)
}

/** Wait until no region is busy and the fonts are ready, then save one PNG per width. */
async function capture(page: Page, name: string, prepare?: () => Promise<void>) {
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 })
    await expect(page.locator('[aria-busy="true"]')).toHaveCount(0)
    if (prepare) await prepare()
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({ path: test.info().outputPath(`${name}-${width}.png`), fullPage: true })
  }
}

test('01 sign-in', async ({ page }) => {
  await routeApi(page, { role: 'admin' })
  await page.goto('/sign-in')
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
  await capture(page, '01-sign-in')
})

test('02 dashboard top and 05 daily values', async ({ page }) => {
  await signedIn(page, { role: 'admin' })
  await page.goto('/dashboard')
  await page.getByText('90 days', { exact: true }).click()
  await expect(page.getByRole('application')).toBeVisible()
  await capture(page, '02-dashboard-top')
  await page.getByText('Daily values', { exact: true }).click()
  await capture(page, '05-dashboard-daily-values')
})

test('03 dashboard contributions', async ({ page }) => {
  await signedIn(page, { role: 'admin' })
  await page.goto('/dashboard')
  await page.getByRole('button', { name: /Palo Verde/ }).first().click()
  await capture(page, '03-dashboard-contributions', async () => {
    await page.getByRole('button', { name: /Palo Verde/ }).first().scrollIntoViewIfNeeded()
  })
})

test('viewer dashboard', async ({ page }) => {
  await signedIn(page, { role: 'viewer' })
  await page.goto('/dashboard')
  await expect(page.getByRole('application')).toBeVisible()
  await capture(page, 'R09-viewer-dashboard')
})

test('06 catalog', async ({ page }) => {
  await signedIn(page, { role: 'admin' })
  await page.goto('/catalog')
  await expect(page.getByText('facility_outages').first()).toBeVisible()
  await capture(page, '06-catalog')
})

for (const [file, key] of [['07-table-facility', 'facility_outages'], ['08-table-generator', 'generator_outages'], ['09-table-national', 'national_outages']] as const) {
  test(`${file}`, async ({ page }) => {
    await signedIn(page, { role: 'admin' })
    await page.goto(`/catalog/${key}`)
    await expect(page.getByRole('region', { name: 'Dataset rows' })).toBeVisible()
    await capture(page, file)
  })
}

test('10 SQL results', async ({ page }) => {
  await signedIn(page, { role: 'admin' })
  await page.goto('/sql')
  await page.getByRole('button', { name: 'Run query', exact: true }).click()
  await expect(page.getByRole('region', { name: 'SQL results' })).toBeVisible()
  await capture(page, '10-sql-explorer')
})

test('11 SQL error', async ({ page }) => {
  await signedIn(page, { role: 'admin', sqlError: true })
  await page.goto('/sql')
  await page.getByRole('button', { name: 'Run query', exact: true }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await capture(page, '11-sql-error')
})

test('12 refresh runs', async ({ page }) => {
  await signedIn(page, { role: 'admin' })
  await page.goto('/refresh')
  await expect(page.getByRole('link', { name: /1044/ }).first()).toBeVisible()
  await capture(page, '12-refresh-runs')
})

test('13 run review and 14 discard dialog', async ({ page }) => {
  await signedIn(page, { role: 'admin' })
  await page.goto(`/refresh/${AWAITING_RUN}`)
  const discard = page.getByRole('button', { name: 'Discard', exact: true })
  await expect(discard).toBeVisible()
  await capture(page, '13-run-review')
  await discard.click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await capture(page, '14-run-discard-dialog')
})

test('15 run failed', async ({ page }) => {
  await signedIn(page, { role: 'admin' })
  await page.goto(`/refresh/${FAILED_RUN}`)
  await expect(page.getByRole('alert').first()).toBeVisible()
  await capture(page, '15-run-failed')
})

test('16 settings', async ({ page }) => {
  await signedIn(page, { role: 'admin' })
  await page.goto('/settings')
  await expect(page.getByRole('switch')).toBeVisible()
  await capture(page, '16-settings-schedule')
})

test('17 viewer unavailable', async ({ page }) => {
  await signedIn(page, { role: 'viewer', published: false })
  await page.goto('/waiting')
  await expect(page.getByRole('heading', { name: 'Nothing to show yet' })).toBeVisible()
  await capture(page, '17-viewer-unavailable')
})

// States without a Figma design. They reuse prototype patterns only (UF-X*).
test('X sign-in error', async ({ page }) => {
  await routeApi(page, { role: 'admin' })
  await page.goto('/sign-in')
  await page.getByLabel('Account').fill('admin')
  await page.getByLabel('Password').fill('wrong')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await capture(page, 'X-sign-in-error')
})

test('X refresh blocked', async ({ page }) => {
  await signedIn(page, { role: 'admin', refreshBlocked: true })
  await page.goto('/refresh')
  await expect(page.getByRole('button', { name: 'Start refresh' })).toBeDisabled()
  await capture(page, 'X-refresh-blocked')
})

test('X SQL empty result', async ({ page }) => {
  await signedIn(page, { role: 'analyst', sqlEmpty: true })
  await page.goto('/sql')
  await page.getByRole('button', { name: 'Run query', exact: true }).click()
  await expect(page.getByText(/0 rows/).first()).toBeVisible()
  await capture(page, 'X-sql-empty')
})

test('320px pages have no page-level horizontal scroll', async ({ page }) => {
  await signedIn(page, { role: 'admin' })
  await page.setViewportSize({ width: 320, height: 800 })
  const overflow: string[] = []
  for (const path of ['/dashboard', '/catalog', '/catalog/facility_outages', '/sql', '/refresh', `/refresh/${AWAITING_RUN}`, '/settings']) {
    await page.goto(path)
    await expect(page.locator('[aria-busy="true"]')).toHaveCount(0)
    const wide = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
    if (wide) overflow.push(path)
  }
  expect(overflow).toEqual([])
  await page.screenshot({ path: test.info().outputPath('320-last.png'), fullPage: true })
})

import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
const env = (globalThis as unknown as { process: { env: Record<string, string | undefined> } }).process.env

test('Viewer dashboard uses real isolated published data and exposes no detail requests', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const paths: string[] = []
  page.on('request', (request) => { if (request.url().includes('/api/v1/')) paths.push(new URL(request.url()).pathname) })
  await page.goto('/sign-in')
  await page.getByLabel('Account', { exact: true }).fill('viewer')
  await page.getByLabel('Password', { exact: true }).fill(env.TRINITY_TEST_VIEWER_PASSWORD ?? '')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('heading', { name: /Range end observation/ })).toBeVisible({ timeout: 30000 })
  await expect(page.getByRole('application')).toBeVisible()
  expect(paths.some((path) => path.includes('facility_outages') || path.includes('generator_outages'))).toBe(false)
  await page.getByRole('button', { name: 'Custom range' }).click()
  await page.getByLabel('From', { exact: true }).fill('2025-01-01')
  await page.getByLabel('To', { exact: true }).fill('2026-01-02')
  await expect(page.getByRole('button', { name: 'Apply range' })).toBeDisabled()
  await page.getByLabel('To', { exact: true }).fill('2024-12-31')
  await expect(page.getByRole('button', { name: 'Apply range' })).toBeDisabled()
  await page.getByRole('button', { name: '90 days', exact: true }).click()
  await expect(page.getByRole('application').getByText('2026-07-06', { exact: true })).toBeVisible({ timeout: 30000 })
  await page.getByRole('application').focus()
  await page.keyboard.press('ArrowRight')
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: 'Selected observation · 2026-07-07' })).toBeVisible()
  expect(await page.evaluate(() => document.getAnimations().filter((animation) => animation.playState === 'running').length)).toBe(0)
  await page.getByRole('button', { name: '30 days', exact: true }).click()
  await expect(page.getByRole('application').getByText('2026-09-04', { exact: true })).toBeVisible({ timeout: 30000 })
  await page.getByRole('button', { name: 'Daily values', exact: true }).click()
  await expect(page.getByRole('columnheader', { name: 'Outage MW' })).toBeVisible()
  await page.getByRole('button', { name: '2026-10-01', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Selected observation · 2026-10-01' })).toBeVisible()
  await page.emulateMedia({ reducedMotion: 'reduce' })
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: 'test-results/dashboard-viewer-1440.png', fullPage: true })
})

test('Analyst loads published tables, exact entity choices, contributions and SQL', async ({ page }) => {
  await page.goto('/sign-in')
  await page.getByLabel('Account', { exact: true }).fill('analyst')
  await page.getByLabel('Password', { exact: true }).fill(env.TRINITY_TEST_ANALYST_PASSWORD ?? '')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('heading', { name: /Reported facility contributions/ })).toBeVisible({ timeout: 30000 })
  await page.getByRole('link', { name: 'Catalog', exact: true }).click()
  await page.getByRole('link', { name: 'generator_outages', exact: true }).click()
  await expect(page.getByRole('combobox', { name: 'Generator', exact: true })).toBeDisabled()
  await expect(page.getByRole('combobox', { name: 'Facility', exact: true }).locator('option[value="001a"]')).toHaveCount(1, { timeout: 30000 })
  await page.getByRole('combobox', { name: 'Facility', exact: true }).selectOption('001a')
  await expect(page.getByRole('combobox', { name: 'Generator', exact: true })).toBeEnabled()
  await expect(page.getByRole('cell', { name: '001a', exact: true }).first()).toBeVisible({ timeout: 30000 })
  await page.getByRole('link', { name: 'SQL Explorer', exact: true }).click()
  await page.getByRole('button', { name: 'Run query', exact: true }).click()
  await expect(page.getByText(/rows · \d+ ms/)).toBeVisible({ timeout: 30000 })
  await expect(page.getByRole('columnheader', { name: 'facilityName', exact: true })).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await page.setViewportSize({ width: 924, height: 1000 })
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: 'test-results/sql-analyst-924.png', fullPage: true })
})

test('real analytical rate admission disables SQL with the server countdown', async ({ page }) => {
  await page.goto('/sign-in')
  await page.getByLabel('Account', { exact: true }).fill('admin')
  await page.getByLabel('Password', { exact: true }).fill(env.TRINITY_TEST_ADMIN_PASSWORD ?? '')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByRole('link', { name: 'SQL Explorer', exact: true }).click()
  const statuses = await page.evaluate(async () => {
    const stored = JSON.parse(sessionStorage.getItem('trinity.session') ?? '{}') as { access_token: string }
    const results: number[] = []
    // Valid request shapes consume admission before SQL policy rejection. This
    // reaches the real rate boundary without starting 31 query containers.
    for (let i = 0; i < 31; i += 1) results.push((await fetch('/api/v1/queries', { method: 'POST', headers: { Authorization: `Bearer ${stored.access_token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ sql: 'DELETE FROM national_outages' }) })).status)
    return results
  })
  expect(statuses.every((status) => status === 422 || status === 429)).toBe(true)
  expect(statuses.at(-1)).toBe(429)
  await page.getByRole('button', { name: 'Run query', exact: true }).click()
  await expect(page.getByRole('button', { name: /Try again in \d+s/ })).toBeDisabled()
  await expect(page.getByText(/Too many requests. Try again in/)).toBeVisible()
})

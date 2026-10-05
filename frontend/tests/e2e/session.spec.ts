import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

// Credentials exist only in this disposable runner's environment. No retained
// persona credentials, tokens, traces or login response bodies become artifacts.
const env = (globalThis as unknown as { process: { env: Record<string, string | undefined> } }).process.env
for (const role of ['viewer', 'analyst', 'admin']) {
  test(`${role}: real login, navigation, logout and accessible waiting/setup screen`, async ({ page }) => {
    await page.goto('/sign-in')
    await page.getByLabel('Account', { exact: true }).fill(role)
    await page.getByLabel('Password', { exact: true }).fill(env[`TRINITY_TEST_${role.toUpperCase()}_PASSWORD`] ?? '')
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    await expect(page).toHaveURL(role === 'admin' ? /\/setup$/ : /\/waiting$/)
    await expect(page.getByRole('link', { name: 'SQL Explorer', exact: true })).toHaveCount(role === 'viewer' ? 0 : 1)
    if (role === 'viewer') {
      await page.goto('/sql'); await expect(page).toHaveURL(/\/waiting$/)
      const status = await page.evaluate(async () => {
        const stored = JSON.parse(sessionStorage.getItem('trinity.session') ?? '{}') as { access_token: string }
        return (await fetch('/api/v1/queries', { method: 'POST', headers: { Authorization: `Bearer ${stored.access_token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ sql: 'SELECT 1' }) })).status
      })
      expect(status).toBe(403)
    }
    if (role === 'analyst') {
      await page.getByRole('link', { name: 'Catalog', exact: true }).click()
      await page.getByRole('link', { name: 'national_outages', exact: true }).click()
      await expect(page.getByRole('heading', { name: 'Nothing to show yet', exact: true })).toBeVisible()
      await page.getByRole('link', { name: 'SQL Explorer', exact: true }).click()
      await page.getByRole('button', { name: 'Run query', exact: true }).click()
      await expect(page.getByRole('heading', { name: 'Nothing to show yet', exact: true })).toBeVisible()
    }
    await page.setViewportSize({ width: 924, height: 900 })
    await page.getByRole('button', { name: '☰ Menu' }).click()
    await expect(page.getByRole('dialog', { name: 'Navigation' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog', { name: 'Navigation' })).toHaveCount(0)
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.getByRole('button', { name: 'Sign out' }).click()
    await expect(page).toHaveURL(/\/sign-in$/)
    expect(await page.evaluate(() => sessionStorage.getItem('trinity.session'))).toBeNull()
    expect(await page.evaluate(() => localStorage.length)).toBe(0)
  })
}
test('real Admin setup, settings and durable refresh start/poll', async ({ page }) => {
  await page.goto('/sign-in')
  await page.getByLabel('Account', { exact: true }).fill('admin')
  await page.getByLabel('Password', { exact: true }).fill(env.TRINITY_TEST_ADMIN_PASSWORD ?? '')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByRole('button', { name: 'Complete setup' }).click()
  await expect(page).toHaveURL(/\/refresh$/)
  await page.getByRole('button', { name: 'Start refresh', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Start refresh', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Run #1' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Progress' })).toBeVisible()
  await expect(page.getByText(/Running/)).toBeVisible()
  // No worker is enabled in this disposable harness. Requested is the actual
  // final state; admission plus repeated real GETs is the evidence boundary.
  let polls = 0
  page.on('request', (request) => { if (request.method() === 'GET' && /\/refresh-runs\/[0-9a-f-]+$/.test(request.url())) polls += 1 })
  await expect.poll(() => polls, { timeout: 8000 }).toBeGreaterThan(1)
})

test('server-revoked session clears the browser session on the next request', async ({ page }) => {
  await page.goto('/sign-in')
  await page.getByLabel('Account', { exact: true }).fill('analyst')
  await page.getByLabel('Password', { exact: true }).fill(env.TRINITY_TEST_ANALYST_PASSWORD ?? '')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page).toHaveURL(/\/waiting$/)
  await page.evaluate(async () => {
    const stored = JSON.parse(sessionStorage.getItem('trinity.session') ?? '{}') as { access_token: string }
    await fetch('/api/v1/auth/logout', { method: 'POST', headers: { Authorization: `Bearer ${stored.access_token}`, 'Content-Type': 'application/json' }, body: '{}' })
  })
  await page.getByRole('link', { name: 'Catalog', exact: true }).click()
  await expect(page).toHaveURL(/\/sign-in$/)
  await expect(page.getByText('Your session ended. Sign in again.')).toBeVisible()
})

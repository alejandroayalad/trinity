/** Simulated auth transport. No retained session is logged out or exported. */
import { expect, test } from '@playwright/test'

const viewer = { user_id: 'synthetic', role: 'viewer', capabilities: ['national:read'], data_ready: false, landing_screen: 'waiting', publication: null, admin_context: null }

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem('trinity.session', JSON.stringify({ access_token: 'synthetic-test-only', expires_at: '2099-01-01T00:00:00Z' })))
})

test('startup performs one /me, waits for Retry-After and retries once without mounting protected content', async ({ page }, testInfo) => {
  let reads = 0
  const paths: string[] = []
  await page.route('**/api/v1/**', (route) => {
    const path = new URL(route.request().url()).pathname
    paths.push(path)
    expect(path).toBe('/api/v1/me')
    reads += 1
    return reads === 1 ? route.fulfill({ status: 503, headers: { 'Retry-After': '2' }, json: { code: 'auth_unavailable' } }) : route.fulfill({ json: viewer })
  })
  await page.goto('/waiting')
  await expect(page.getByRole('button', { name: 'Retry after 2s', exact: true })).toBeDisabled()
  expect(reads).toBe(1)
  await expect(page.getByRole('navigation')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Retry', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Nothing to show yet', exact: true })).toBeVisible()
  expect(reads).toBe(2)
  await testInfo.attach('startup-request-counts', { body: JSON.stringify({ reads, paths }), contentType: 'application/json' })
})

for (const failure of ['server', 'network']) {
  test(`logout ${failure} failure visibly distinguishes local sign-out from unconfirmed revocation`, async ({ page }, testInfo) => {
    let reads = 0, writes = 0
    await page.route('**/api/v1/**', (route) => {
      const path = new URL(route.request().url()).pathname
      if (path === '/api/v1/me') { reads += 1; return route.fulfill({ json: viewer }) }
      expect(path).toBe('/api/v1/auth/logout')
      writes += 1
      return failure === 'server' ? route.fulfill({ status: 503, json: { code: 'auth_unavailable' } }) : route.abort('connectionfailed')
    })
    await page.goto('/waiting')
    await expect(page.getByRole('heading', { name: 'Nothing to show yet', exact: true })).toBeVisible()
    expect(reads).toBe(1)
    await page.getByRole('button', { name: 'Sign out', exact: true }).click()
    await expect(page).toHaveURL(/\/sign-in$/)
    await expect(page.getByRole('alert')).toContainText('server revocation could not be confirmed')
    await expect(page.getByRole('alert')).toContainText('may remain valid until it expires')
    expect(await page.evaluate(() => sessionStorage.getItem('trinity.session') === null)).toBe(true)
    await expect(page.getByRole('navigation')).toHaveCount(0)
    expect(writes).toBe(1)
    await page.screenshot({ path: testInfo.outputPath(`logout-${failure}-unconfirmed.png`) })
    await testInfo.attach('request-counts', { body: JSON.stringify({ reads, writes, failure: 'simulated' }), contentType: 'application/json' })
  })
}

test('confirmed logout clears local storage and reports server revocation', async ({ page }) => {
  await page.route('**/api/v1/**', (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/v1/me') return route.fulfill({ json: viewer })
    expect(path).toBe('/api/v1/auth/logout')
    return route.fulfill({ status: 204 })
  })
  await page.goto('/waiting')
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await expect(page.getByText('Signed out. The server session was revoked.', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('trinity.session') === null)).toBe(true)
})

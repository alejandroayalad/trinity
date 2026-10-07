import { defineConfig } from '@playwright/test'

// Visual fidelity captures. The dev server must already run on 5173; every
// API call is a synthetic page.route reply, so no backend is needed.
export default defineConfig({
  testDir: '.', testMatch: 'fidelity.spec.ts', workers: 1, retries: 0,
  outputDir: '../../test-results/ui-fidelity',
  use: { baseURL: 'http://127.0.0.1:5173', headless: true, trace: 'off', screenshot: 'off', video: 'off' },
  reporter: [['list']],
})

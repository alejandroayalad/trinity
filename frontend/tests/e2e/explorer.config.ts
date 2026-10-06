import { defineConfig } from '@playwright/test'

// Use the running application. Keep the original live-QA evidence untouched.
export default defineConfig({
  testDir: '.', testMatch: 'explorer-state.spec.ts', workers: 1, retries: 0,
  outputDir: '../../test-results/explorer-state-2026-10-06',
  use: { baseURL: 'http://127.0.0.1:5173', headless: true, trace: 'off', screenshot: 'off', video: 'off' },
  reporter: [['list'], ['json', { outputFile: '../../test-results/explorer-state-2026-10-06/results.json' }]],
})

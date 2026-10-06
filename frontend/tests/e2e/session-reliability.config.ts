import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: '.', testMatch: 'session-reliability.spec.ts', workers: 1, retries: 0,
  outputDir: '../../test-results/session-reliability-2026-10-06',
  use: { baseURL: 'http://127.0.0.1:5173', headless: true, trace: 'off', screenshot: 'off', video: 'off' },
  reporter: [['list'], ['json', { outputFile: '../../test-results/session-reliability-2026-10-06/results.json' }]],
})

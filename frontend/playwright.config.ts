import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e', workers: 1, retries: 0,
  use: { baseURL: 'http://127.0.0.1:5175', headless: true, trace: 'off', screenshot: 'off', video: 'off' },
  reporter: 'list',
  webServer: { command: 'npm run dev -- --port 5175', url: 'http://127.0.0.1:5175', reuseExistingServer: false },
})

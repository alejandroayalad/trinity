/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// The browser calls only relative /api/v1/... paths. In development, Vite
// forwards those requests to the local API. The browser therefore sees one
// origin, and the backend needs no CORS setting for local work.
//
// The default target is the Docker Compose API on 127.0.0.1:8000. Browser
// tests can set TRINITY_API_TARGET to use a disposable API on another port.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', 'TRINITY_')
  const apiTarget = env.TRINITY_API_TARGET ?? 'http://127.0.0.1:8000'
  const proxy = { '/api': { target: apiTarget } }
  // Unit tests read ../docs/openapi.json to compare enums with the contract.
  // Only test mode may read outside this folder; the dev server may not.
  const fs = mode === 'test' ? { allow: ['.', '../docs'] } : undefined
  return {
    plugins: [react()],
    server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy, fs },
    preview: { host: '127.0.0.1', port: 4173, strictPort: true, proxy },
    test: {
      environment: 'jsdom',
      setupFiles: ['src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
      restoreMocks: true,
      unstubGlobals: true,
    },
  }
})

import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach } from 'vitest'

/**
 * jsdom does not implement matchMedia. The stub reports "no match" for every
 * query, so tests start on a wide screen without reduced motion. A test that
 * needs another answer calls setMediaMatches().
 */
let matchingQueries = new Set<string>()

export function setMediaMatches(queries: string[]): void {
  matchingQueries = new Set(queries)
}

// The lint test runs in plain Node.js, where no window exists.
const hasWindow = typeof window !== 'undefined'

beforeEach(() => {
  if (!hasWindow) return
  matchingQueries = new Set()
  window.matchMedia = (query: string) =>
    ({
      matches: matchingQueries.has(query),
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }) as MediaQueryList
})

afterEach(() => {
  if (!hasWindow) return
  cleanup()
  window.sessionStorage.clear()
  window.localStorage.clear()
})

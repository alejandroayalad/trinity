/**
 * Session token storage (spec D01).
 *
 * The browser keeps the token and its expiry under one sessionStorage key.
 * sessionStorage survives a reload of the tab and is removed when the tab
 * closes; a new tab starts signed out. The token is never written to
 * localStorage, a cookie, a URL or a log. Only api/client.ts reads it.
 *
 * Browsers can refuse storage (private modes, quota). Every access is
 * therefore wrapped in try/catch, and an in-memory copy keeps the session for
 * the current page view.
 */

const STORAGE_KEY = 'trinity.session'

export type StoredSession = {
  readonly accessToken: string
  readonly expiresAt: string
}

let memoryCopy: StoredSession | null = null

function parseStored(text: string): StoredSession | null {
  try {
    const value: unknown = JSON.parse(text)
    if (typeof value !== 'object' || value === null) return null
    const record = value as Record<string, unknown>
    if (typeof record.access_token !== 'string' || typeof record.expires_at !== 'string') return null
    return { accessToken: record.access_token, expiresAt: record.expires_at }
  } catch {
    return null
  }
}

/** Return true when expiresAt has passed or cannot be read. The server still enforces expiry. */
export function isExpired(session: StoredSession, now: number = Date.now()): boolean {
  const expiry = Date.parse(session.expiresAt)
  return Number.isNaN(expiry) || expiry <= now
}

/** Read the stored session, or the memory copy when storage is unavailable. */
function readSession(): StoredSession | null {
  try {
    const text = window.sessionStorage.getItem(STORAGE_KEY)
    if (text !== null) return parseStored(text)
  } catch {
    // Storage is unavailable. Use the memory copy for this page view.
  }
  return memoryCopy
}

/** Return the current unexpired session. An expired session is cleared here. */
export function loadSession(now: number = Date.now()): StoredSession | null {
  const session = readSession()
  if (session === null) return null
  if (isExpired(session, now)) {
    clearSession()
    return null
  }
  return session
}

export function saveSession(session: StoredSession): void {
  memoryCopy = session
  try {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ access_token: session.accessToken, expires_at: session.expiresAt }),
    )
  } catch {
    // Storage is unavailable. The memory copy keeps the session until reload.
  }
}

export function clearSession(): void {
  memoryCopy = null
  try {
    window.sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // Nothing is stored when storage is unavailable.
  }
}

/** Return the bearer token of the current unexpired session, or null. */
export function getAccessToken(): string | null {
  return loadSession()?.accessToken ?? null
}

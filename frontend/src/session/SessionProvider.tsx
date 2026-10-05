import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { getMe, login, logout } from '../api/endpoints'
import { setPublicationListener, setUnauthorizedHandler } from '../api/client'
import type { MeResponse } from '../api/types'
import { clearSession, loadSession, saveSession } from './session'

type SessionContextValue = {
  me: MeResponse | null; loading: boolean; error: unknown; reason: string
  signIn: (username: string, password: string) => Promise<void>
  signOut: () => Promise<void>; refresh: () => Promise<void>
}
const SessionContext = createContext<SessionContextValue | null>(null)

/** Verify the stored token before mounting pages. Clear all private cache on session loss. */
export function SessionProvider({ children }: { children: ReactNode }) {
  const cache = useQueryClient()
  const [me, setMe] = useState<MeResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<unknown>(null)
  const [reason, setReason] = useState('')
  const generation = useRef(0)
  const publication = useRef<string | null | undefined>(undefined)
  const superseded = useRef(new Set<string | null>())
  const end = useCallback((message = '') => {
    // Late HTTP replies from the previous account must not reopen its session.
    generation.current += 1
    clearSession()
    cache.clear()
    publication.current = undefined
    superseded.current.clear()
    setMe(null)
    setLoading(false)
    setError(null)
    setReason(message)
  }, [cache])
  const refresh = useCallback(async () => {
    const ownGeneration = generation.current
    const result = await getMe()
    if (ownGeneration === generation.current) setMe(result.data)
  }, [])
  useEffect(() => {
    let active = true
    setUnauthorizedHandler(() => end('Your session ended. Sign in again.'))
    setPublicationListener((id) => {
      if (superseded.current.has(id)) return
      const previous = publication.current
      if (previous !== undefined && previous !== id) superseded.current.add(previous)
      publication.current = id
      if (previous !== undefined && previous !== id) {
        void cache.invalidateQueries()
        void refresh().catch(() => undefined)
      }
    })
    const stored = loadSession()
    if (stored) {
      const startupGeneration = generation.current
      // A 401 already ended this generation. Its rejected startup promise must
      // not replace the sign-in page with a stale error screen.
      void refresh().catch((failure: unknown) => { if (active && startupGeneration === generation.current) setError(failure) })
        .finally(() => { if (active) setLoading(false) })
    } else {
      // Queue the start-up transition so StrictMode can dispose its first effect.
      queueMicrotask(() => { if (active) setLoading(false) })
    }
    return () => { active = false; setUnauthorizedHandler(null); setPublicationListener(null) }
  }, [cache, end, refresh])
  useEffect(() => {
    // This also covers tokens that expire while a tab was suspended.
    const timer = window.setInterval(() => {
      if (me !== null && loadSession() === null) end('Your session ended. Sign in again.')
    }, 250)
    return () => window.clearInterval(timer)
  }, [end, me])
  const signIn = async (username: string, password: string) => {
    end()
    const ownGeneration = generation.current
    const result = await login(username, password)
    if (ownGeneration !== generation.current) return
    saveSession({ accessToken: result.data.access_token, expiresAt: result.data.expires_at })
    try { await refresh() } catch (failure) { end(); throw failure }
  }
  const signOut = async () => {
    // Dispatch logout while the token exists, then remove local authority immediately.
    const pending = logout()
    end()
    await pending.catch(() => undefined)
  }
  return <SessionContext.Provider value={{ me, loading, error, reason, signIn, signOut, refresh }}>{children}</SessionContext.Provider>
}

export function useSession() {
  const value = useContext(SessionContext)
  if (!value) throw new Error('SessionProvider is required.')
  return value
}

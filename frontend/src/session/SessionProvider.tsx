import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { getMe, login, logout } from '../api/endpoints'
import { isApiError, setPublicationListener, setUnauthorizedHandler } from '../api/client'
import type { MeResponse } from '../api/types'
import { clearSession, loadSession, saveSession } from './session'

type LogoutState = 'idle' | 'pending' | 'confirmed' | 'unconfirmed'

type SessionContextValue = {
  me: MeResponse | null; loading: boolean; error: unknown; reason: string; logoutState: LogoutState
  signIn: (username: string, password: string) => Promise<void>
  signOut: () => Promise<void>; refresh: () => Promise<void>; retryStartup: () => Promise<void>
}
const SessionContext = createContext<SessionContextValue | null>(null)

/** Verify the stored token before mounting pages. Clear all private cache on session loss. */
export function SessionProvider({ children }: { children: ReactNode }) {
  const cache = useQueryClient()
  const [me, setMe] = useState<MeResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<unknown>(null)
  const [reason, setReason] = useState('')
  const [logoutState, setLogoutState] = useState<LogoutState>('idle')
  const meRequest = useRef<{ generation: number; promise: Promise<void> } | null>(null)
  const logoutRequest = useRef<Promise<void> | null>(null)
  const generation = useRef(0)
  const publication = useRef<string | null | undefined>(undefined)
  const superseded = useRef(new Set<string | null>())
  const end = useCallback((message = '') => {
    // Late HTTP replies from the previous account must not reopen its session.
    generation.current += 1
    logoutRequest.current = null
    clearSession()
    cache.clear()
    publication.current = undefined
    superseded.current.clear()
    setMe(null)
    setLoading(false)
    setError(null)
    setReason(message)
    setLogoutState('idle')
  }, [cache])
  const refresh = useCallback((): Promise<void> => {
    const ownGeneration = generation.current
    // StrictMode replays effects. Share only the current in-flight request,
    // never cache completed role/session authority across later checks.
    if (meRequest.current?.generation === ownGeneration) return meRequest.current.promise
    const promise = getMe().then((result) => {
      if (ownGeneration !== generation.current) return
      if (!loadSession()) { end('Your session ended. Sign in again.'); return }
      setMe(result.data)
    }).catch((failure: unknown) => {
      // Expiry can remove the token while this request is pending. End only
      // this generation; a late denial must not clear a replacement session.
      if (ownGeneration === generation.current && isApiError(failure) && failure.status === 401) end('Your session ended. Sign in again.')
      throw failure
    }).finally(() => {
      if (meRequest.current?.promise === promise) meRequest.current = null
    })
    meRequest.current = { generation: ownGeneration, promise }
    return promise
  }, [end])
  const retryStartup = async () => {
    if (!loadSession()) { end('Your session ended. Sign in again.'); return }
    const ownGeneration = generation.current
    setLoading(true); setError(null)
    try { await refresh() }
    catch (failure) { if (ownGeneration === generation.current) setError(failure) }
    finally { if (ownGeneration === generation.current) setLoading(false) }
  }
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
        .finally(() => { if (active && startupGeneration === generation.current) setLoading(false) })
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
  const signOut = (): Promise<void> => {
    if (logoutRequest.current) return logoutRequest.current
    // Send the current token once, then remove local authority immediately.
    // A failed server write is not proof of revocation. Keep its uncertainty
    // visible without retaining a token or automatically replaying the POST.
    const pending = logout()
    end('Signed out on this device. Confirming server revocation…')
    const ownGeneration = generation.current
    setLogoutState('pending')
    const operation = pending.then((result) => {
      if (result.status !== 204) throw new Error('Revocation was not confirmed')
      if (ownGeneration !== generation.current) return
      setLogoutState('confirmed')
      setReason('Signed out. The server session was revoked.')
    }).catch((failure: unknown) => {
      if (ownGeneration !== generation.current) return
      if (isApiError(failure) && failure.status === 401) {
        setLogoutState('confirmed')
        setReason('Signed out. The server session is no longer valid.')
      } else {
        setLogoutState('unconfirmed')
        setReason('Signed out on this device, but server revocation could not be confirmed. The server session may remain valid until it expires.')
      }
    }).finally(() => { if (logoutRequest.current === operation) logoutRequest.current = null })
    logoutRequest.current = operation
    return operation
  }
  return <SessionContext.Provider value={{ me, loading, error, reason, logoutState, signIn, signOut, refresh, retryStartup }}>{children}</SessionContext.Provider>
}

export function useSession() {
  const value = useContext(SessionContext)
  if (!value) throw new Error('SessionProvider is required.')
  return value
}

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, expect, test, vi } from 'vitest'
import { SessionProvider, useSession } from './SessionProvider'
import { clearSession, saveSession } from './session'
import { RequireCapability } from './capabilities'
import { SignIn } from '../pages/signin/SignIn'
import { AppShell } from '../shell/AppShell'
import { json, problem, stubFetch } from '../test/fetchStub'
import type { MeResponse } from '../api/types'

const viewer: MeResponse = { user_id: 'viewer-id', role: 'viewer', capabilities: ['national:read'], data_ready: false, landing_screen: 'waiting', publication: null, admin_context: null }
afterEach(() => { clearSession(); vi.useRealTimers() })
function mount(path = '/sign-in') {
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={cache}><MemoryRouter initialEntries={[path]}><SessionProvider><Routes><Route path="/sign-in" element={<SignIn />} /><Route element={<RequireCapability />}><Route element={<AppShell />}><Route path="/waiting" element={<p>Waiting for publication</p>} /><Route element={<RequireCapability capability="sql:execute" />}><Route path="/sql" element={<p>Forbidden page</p>} /></Route></Route></Route></Routes></SessionProvider></MemoryRouter></QueryClientProvider>)
  return cache
}
test('sign-in clears the password after rejected credentials', async () => {
  stubFetch({ 'POST /api/v1/auth/login': problem(401, 'invalid_credentials') })
  mount(); await screen.findByLabelText('Account')
  fireEvent.change(screen.getByLabelText('Account'), { target: { value: 'viewer' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'test-only' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  await screen.findByText('Account or password is incorrect.')
  expect(screen.getByLabelText('Password')).toHaveValue('')
})
test('stored authority is checked before a denied page mounts; drawer closes with Escape', async () => {
  saveSession({ accessToken: 'synthetic', expiresAt: '2099-01-01T00:00:00Z' })
  const { calls } = stubFetch({ 'GET /api/v1/me': json(200, viewer) })
  mount('/sql'); await screen.findByText('Waiting for publication')
  expect(screen.queryByText('Forbidden page')).not.toBeInTheDocument()
  expect(calls.map((c) => c.path)).toEqual(['/api/v1/me'])
  expect(screen.queryByRole('link', { name: 'SQL Explorer' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '☰ Menu' }))
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  fireEvent.keyDown(document, { key: 'Escape' })
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})
test('revocation removes cached private data and returns to sign-in', async () => {
  saveSession({ accessToken: 'synthetic', expiresAt: '2099-01-01T00:00:00Z' })
  stubFetch({ 'GET /api/v1/me': problem(401, 'invalid_session') })
  const cache = mount('/sql'); cache.setQueryData(['private'], ['sensitive synthetic row'])
  await screen.findByText('Your session ended. Sign in again.')
  await screen.findByLabelText('Account')
  await waitFor(() => expect(cache.getQueryData(['private'])).toBeUndefined())
  expect(sessionStorage.getItem('trinity.session')).toBeNull()
})
test('expiry clears the session without waiting for another HTTP request', async () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-05T00:00:00Z'))
  saveSession({ accessToken: 'synthetic', expiresAt: '2026-10-05T00:00:01Z' })
  stubFetch({ 'GET /api/v1/me': json(200, viewer) })
  function Probe() { const s = useSession(); return <p>{s.me ? 'active' : s.reason || 'starting'}</p> }
  render(<QueryClientProvider client={new QueryClient()}><SessionProvider><Probe /></SessionProvider></QueryClientProvider>)
  await act(async () => { await vi.advanceTimersByTimeAsync(500) })
  expect(screen.getByText('active')).toBeInTheDocument()
  await act(async () => { await vi.advanceTimersByTimeAsync(750) })
  expect(screen.getByText('Your session ended. Sign in again.')).toBeInTheDocument()
})

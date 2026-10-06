import { StrictMode } from 'react'
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
function mount(path = '/sign-in', strict = false) {
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const content = <QueryClientProvider client={cache}><MemoryRouter initialEntries={[path]}><SessionProvider><Routes><Route path="/sign-in" element={<SignIn />} /><Route element={<RequireCapability />}><Route element={<AppShell />}><Route path="/waiting" element={<p>Waiting for publication</p>} /><Route element={<RequireCapability capability="sql:execute" />}><Route path="/sql" element={<p>Forbidden page</p>} /></Route></Route></Route></Routes></SessionProvider></MemoryRouter></QueryClientProvider>
  render(strict ? <StrictMode>{content}</StrictMode> : content)
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

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}
function storedSession() { saveSession({ accessToken: 'synthetic', expiresAt: '2099-01-01T00:00:00Z' }) }

test('StrictMode startup shares one pending /me before mounting protected content', async () => {
  storedSession()
  const response = deferred<Response>()
  const { calls } = stubFetch({ 'GET /api/v1/me': () => response.promise })
  mount('/waiting', true)
  expect(calls).toHaveLength(1)
  expect(screen.queryByText('Waiting for publication')).not.toBeInTheDocument()
  await act(async () => { response.resolve(json(200, viewer)); await response.promise })
  await screen.findByText('Waiting for publication')
  expect(calls).toHaveLength(1)
})

test.each(['/waiting', '/sign-in'])('failed startup at %s offers one manual Retry and keeps protected content closed', async (path) => {
  storedSession()
  const response = deferred<Response>()
  const { calls } = stubFetch({ 'GET /api/v1/me': [problem(503, 'auth_unavailable'), () => response.promise] })
  mount(path, true)
  const retry = await screen.findByRole('button', { name: 'Retry' })
  expect(calls).toHaveLength(1)
  expect(screen.queryByText('Waiting for publication')).not.toBeInTheDocument()
  fireEvent.click(retry); fireEvent.click(retry)
  expect(calls).toHaveLength(2)
  expect(screen.queryByText('Waiting for publication')).not.toBeInTheDocument()
  await act(async () => { response.resolve(json(200, viewer)); await response.promise })
  await screen.findByText('Waiting for publication')
  expect(calls).toHaveLength(2)
})

test('startup Retry that receives 401 clears local authority without another Retry', async () => {
  storedSession()
  const { calls } = stubFetch({ 'GET /api/v1/me': [problem(503, 'auth_unavailable'), problem(401, 'invalid_session')] })
  mount('/waiting', true)
  fireEvent.click(await screen.findByRole('button', { name: 'Retry' }))
  await screen.findByLabelText('Account')
  expect(screen.getByText('Your session ended. Sign in again.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
  expect(sessionStorage.getItem('trinity.session')).toBeNull()
  expect(calls).toHaveLength(2)
})

test.each(['server', 'network'])('failed %s revocation clears local data but reports uncertainty', async (kind) => {
  storedSession()
  const { calls } = stubFetch({
    'GET /api/v1/me': json(200, viewer),
    'POST /api/v1/auth/logout': kind === 'server' ? problem(503, 'auth_unavailable') : () => { throw new TypeError('synthetic offline transport') },
  })
  const cache = mount('/waiting')
  await screen.findByText('Waiting for publication')
  cache.setQueryData(['private'], ['synthetic private row'])
  const button = screen.getByRole('button', { name: 'Sign out' })
  fireEvent.click(button); fireEvent.click(button)
  await screen.findByText(/server revocation could not be confirmed/)
  expect(screen.getByRole('alert')).toHaveTextContent('may remain valid until it expires')
  expect(sessionStorage.getItem('trinity.session')).toBeNull()
  expect(cache.getQueryData(['private'])).toBeUndefined()
  expect(screen.queryByText('Waiting for publication')).not.toBeInTheDocument()
  expect(calls.filter((call) => call.path.endsWith('/auth/logout'))).toHaveLength(1)
  expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled()
})

test.each([204, 401])('logout status %s confirms an ended server session', async (status) => {
  storedSession()
  stubFetch({ 'GET /api/v1/me': json(200, viewer), 'POST /api/v1/auth/logout': status === 204 ? new Response(null, { status: 204 }) : problem(401, 'invalid_session') })
  mount('/waiting')
  fireEvent.click(await screen.findByRole('button', { name: 'Sign out' }))
  await screen.findByText(status === 204 ? 'Signed out. The server session was revoked.' : 'Signed out. The server session is no longer valid.')
  expect(sessionStorage.getItem('trinity.session')).toBeNull()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('pending logout shows confirmation in progress and prevents a second sign-in', async () => {
  storedSession()
  const response = deferred<Response>()
  stubFetch({ 'GET /api/v1/me': json(200, viewer), 'POST /api/v1/auth/logout': () => response.promise })
  mount('/waiting')
  fireEvent.click(await screen.findByRole('button', { name: 'Sign out' }))
  await screen.findByText('Signed out on this device. Confirming server revocation…')
  expect(screen.getByRole('button', { name: 'Sign in' })).toBeDisabled()
  expect(sessionStorage.getItem('trinity.session')).toBeNull()
  await act(async () => { response.resolve(problem(503, 'auth_unavailable')); await response.promise })
  await screen.findByText(/server revocation could not be confirmed/)
})

test.each([200, 401])('a delayed startup %s after logout cannot restore authority or hide revocation failure', async (status) => {
  storedSession()
  const response = deferred<Response>()
  const { calls } = stubFetch({ 'GET /api/v1/me': () => response.promise, 'POST /api/v1/auth/logout': problem(503, 'auth_unavailable') })
  function Probe() {
    const session = useSession()
    return <><button onClick={() => void session.signOut()}>End session</button><p>{session.reason}</p><p>{session.me ? 'protected' : 'closed'}</p></>
  }
  render(<QueryClientProvider client={new QueryClient()}><StrictMode><SessionProvider><Probe /></SessionProvider></StrictMode></QueryClientProvider>)
  fireEvent.click(screen.getByRole('button', { name: 'End session' }))
  await screen.findByText(/server revocation could not be confirmed/)
  await act(async () => { response.resolve(status === 200 ? json(200, viewer) : problem(401, 'invalid_session')); await response.promise })
  expect(screen.queryByText('protected')).not.toBeInTheDocument()
  expect(screen.getByText(/server revocation could not be confirmed/)).toBeInTheDocument()
  expect(calls.filter((call) => call.path.endsWith('/me'))).toHaveLength(1)
})

test('a completed /me is not cached as authority for the next refresh', async () => {
  storedSession()
  const { calls } = stubFetch({ 'GET /api/v1/me': [json(200, viewer), problem(401, 'invalid_session')] })
  function Probe() {
    const session = useSession()
    return <><p>{session.me ? 'active session' : session.reason}</p><button onClick={() => { void session.refresh().catch(() => undefined) }}>Refresh authority</button></>
  }
  render(<QueryClientProvider client={new QueryClient()}><SessionProvider><Probe /></SessionProvider></QueryClientProvider>)
  await screen.findByText('active session')
  fireEvent.click(screen.getByRole('button', { name: 'Refresh authority' }))
  await screen.findByText('Your session ended. Sign in again.')
  expect(calls).toHaveLength(2)
})

test.each([200, 401])('startup reply %s after expiry cannot open protected content', async (status) => {
  vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-06T00:00:00Z'))
  saveSession({ accessToken: 'synthetic', expiresAt: '2026-10-06T00:00:01Z' })
  const response = deferred<Response>()
  stubFetch({ 'GET /api/v1/me': () => response.promise })
  mount('/waiting', true)
  await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
  await act(async () => { response.resolve(status === 200 ? json(200, viewer) : problem(401, 'invalid_session')); await response.promise })
  vi.useRealTimers()
  await screen.findByText('Your session ended. Sign in again.')
  expect(screen.queryByText('Waiting for publication')).not.toBeInTheDocument()
})

test('an old logout failure cannot overwrite a replacement session', async () => {
  storedSession()
  const response = deferred<Response>()
  const { calls } = stubFetch({
    'GET /api/v1/me': [json(200, viewer), json(200, { ...viewer, user_id: 'replacement' })],
    'POST /api/v1/auth/logout': () => response.promise,
    'POST /api/v1/auth/login': json(200, { access_token: 'synthetic-replacement', expires_at: '2099-01-01T00:00:00Z' }),
  })
  function Probe() {
    const session = useSession()
    return <><p>{session.me?.user_id ?? session.reason}</p><button onClick={() => void session.signOut()}>End session</button><button onClick={() => void session.signIn('viewer', 'synthetic-only')}>Replace session</button></>
  }
  render(<QueryClientProvider client={new QueryClient()}><SessionProvider><Probe /></SessionProvider></QueryClientProvider>)
  await screen.findByText('viewer-id')
  fireEvent.click(screen.getByRole('button', { name: 'End session' }))
  fireEvent.click(screen.getByRole('button', { name: 'Replace session' }))
  await screen.findByText('replacement')
  await act(async () => { response.resolve(problem(503, 'auth_unavailable')); await response.promise })
  expect(screen.getByText('replacement')).toBeInTheDocument()
  expect(screen.queryByText(/server revocation could not be confirmed/)).not.toBeInTheDocument()
  expect(calls.filter((call) => call.path.endsWith('/me'))).toHaveLength(2)
})

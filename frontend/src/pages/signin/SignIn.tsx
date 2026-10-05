import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router'
import { useSession } from '../../session/SessionProvider'
import { landingPath } from '../../session/capabilities'
import { Button } from '../../components/controls/Button'
import { ErrorState, LoadingRows } from '../../components/feedback/States'

export function SignIn() {
  const { me, loading, reason, signIn } = useSession()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  if (loading) return <LoadingRows />
  if (me) return <Navigate to={landingPath(me.landing_screen)} replace />
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError(null)
    try { await signIn(username, password) } catch (failure) { setError(failure) }
    finally { setPassword(''); setBusy(false) }
  }
  return <main className="sign-in page-enter"><form className="panel stack" onSubmit={(event) => { void submit(event) }}>
    <img className="wordmark" src="/brand/wordmark.png" alt="Trinity" />
    <h1>Sign in</h1><p className="muted">Explore U.S. nuclear outage data.</p>
    {reason && <p role="status">{reason}</p>}{error !== null && <ErrorState error={error} />}
    <label>Account<input autoComplete="username" required value={username} onChange={(e) => setUsername(e.target.value)} /></label>
    <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
    <Button type="submit" variant="primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</Button>
    <p className="muted">Use your assigned local account.</p>
  </form></main>
}

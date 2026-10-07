import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router'
import { useSession } from '../../session/SessionProvider'
import { landingPath } from '../../session/capabilities'
import { PageError } from '../shared'
import { Button } from '../../components/controls/Button'
import { Field, inputClass } from '../../components/controls/Field'
import { BrandLockup } from '../../components/brand/BrandLockup'
import { Callout } from '../../components/feedback/Callout'
import { LoadingRows } from '../../components/feedback/States'
import { errorMessage } from '../../api/messages'
import styles from './SignIn.module.css'

/**
 * The sign-in card (spec UF-A01–A06). A startup failure shows in the same
 * card with Retry. A session or sign-out message shows above the form.
 */
export function SignIn() {
  const { me, loading, error: startupError, reason, logoutState, signIn, retryStartup } = useSession()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  if (loading) return <main className={styles.page}><div className={styles.card}><LoadingRows /></div></main>
  if (startupError) return <main className={styles.page}><div className={styles.card}><BrandLockup size="signin" /><div className={styles.startup}><PageError error={startupError} onRetry={retryStartup} /></div></div></main>
  if (me) return <Navigate to={landingPath(me.landing_screen)} replace />
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError(null)
    try { await signIn(username, password) } catch (failure) { setError(failure) }
    finally { setPassword(''); setBusy(false) }
  }
  return <main className={[styles.page, 'page-enter'].join(' ')}><div className={styles.card}>
    <BrandLockup size="signin" />
    <h1 className={styles.brandLine}>Three levels. One clear view.</h1>
    <p className={styles.lead}>Sign in with your account.</p>
    {reason && <div className={styles.message}>{logoutState === 'unconfirmed' ? <div role="alert"><Callout tone="warning">{reason}</Callout></div> : <div role="status"><Callout tone="info">{reason}</Callout></div>}</div>}
    <form className={styles.form} onSubmit={(event) => { void submit(event) }}>
      <Field label="Account"><input className={inputClass} autoComplete="username" required value={username} onChange={(e) => setUsername(e.target.value)} /></Field>
      <Field label="Password"><input className={inputClass} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
      {error !== null && <div role="alert" className={styles.error}><span aria-hidden="true">✕</span><span>{errorMessage(error)}</span></div>}
      <Button type="submit" variant="primary" size="full" disabled={busy || logoutState === 'pending'}>{busy ? 'Signing in…' : 'Sign in'}</Button>
    </form>
  </div></main>
}

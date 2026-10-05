import type { ReactNode } from 'react'
import { errorMessage } from '../../api/messages'
import { Callout } from './Callout'
import styles from './States.module.css'

/** Three skeleton bars and a hidden "Loading…" status, as in the handoff. */
export function LoadingRows({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className={styles.skeleton} aria-busy="true">
      <span className="sr-only" role="status">
        {label}
      </span>
      <div className={styles.bar} />
      <div className={styles.bar} />
      <div className={styles.bar} />
    </div>
  )
}

/** A dashed box for an empty but successful result. */
export function EmptyState({ children }: { children: ReactNode }) {
  return <div className={styles.empty}>{children}</div>
}

/** The red callout with the safe message for an API error. */
export function ErrorState({ error, title }: { error: unknown; title?: string }) {
  return (
    <Callout tone="error" title={title ?? '✕ Error'}>
      {errorMessage(error)}
    </Callout>
  )
}

/**
 * Handoff A2 "Nothing to show yet": the state of an analytical page before
 * the first publication (spec R60). `action` is the Admin-only "Go to Refresh".
 */
export function NothingToShow({ action }: { action?: ReactNode }) {
  return (
    <div className={styles.unavailable}>
      <img src="/brand/mark-slate.png" alt="" className={styles.unavailableMark} />
      <h1 className={styles.unavailableTitle}>Nothing to show yet</h1>
      <p className={styles.unavailableText}>An admin still needs to publish the first set of data.</p>
      {action !== undefined && <div className={styles.unavailableAction}>{action}</div>}
    </div>
  )
}

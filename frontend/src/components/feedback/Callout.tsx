import type { ReactNode } from 'react'
import styles from './Callout.module.css'

type CalloutProps = { tone: 'warning' | 'error' | 'success' | 'info'; title?: string; children: ReactNode; className?: string }

/**
 * A message block. Errors use role="alert" so screen readers announce them at
 * once; warnings and notes use role="note".
 */
export function Callout({ tone, title, children, className }: CalloutProps) {
  return (
    <div role={tone === 'error' ? 'alert' : 'note'} className={[styles.callout, styles[tone], className ?? ''].join(' ')}>
      {title !== undefined && <strong className={styles.title}>{title}</strong>}
      <span>{children}</span>
    </div>
  )
}

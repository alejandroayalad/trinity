import type { ReactNode } from 'react'
import styles from './Badge.module.css'

export type Tone = 'success' | 'warning' | 'error' | 'neutral' | 'running'

type StatusBadgeProps = { tone: Tone; glyph: string; children: ReactNode; large?: boolean }

/**
 * A status pairs a color with a glyph and a text label, so color is never the
 * only signal: ✓ Published, ✕ Failed, ! Awaiting review, ◐ Running.
 */
export function StatusBadge({ tone, glyph, children, large = false }: StatusBadgeProps) {
  return (
    <span className={[styles.badge, styles[tone], large ? styles.large : ''].join(' ')}>
      <span aria-hidden="true">{glyph}</span>
      {children}
    </span>
  )
}

export function Tag({ children, pinned = false }: { children: ReactNode; pinned?: boolean }) {
  return <span className={[styles.tag, pinned ? styles.tagPinned : ''].join(' ')}>{children}</span>
}

/**
 * The missing-value chip. A null value is "not reported", which differs from
 * a reported 0 (spec R16). SQL results use the "NULL" label (spec D04).
 */
export function MissingChip({ label = '○ Not reported' }: { label?: string }) {
  return <span className={styles.missing}>{label}</span>
}

/** Plain muted text for a value that cannot be calculated, such as a share with zero capacity. */
export function UnavailableValue({ children = 'Unavailable' }: { children?: ReactNode }) {
  return <span className={styles.unavailable}>{children}</span>
}

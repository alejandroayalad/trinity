import type { ReactNode } from 'react'
import styles from './StepTimeline.module.css'

export type StepState = 'done' | 'running' | 'failed' | 'attention' | 'pending' | 'discarded'

const CIRCLE: Record<StepState, { glyph: string; label: string }> = {
  done: { glyph: '✓', label: 'Done' },
  running: { glyph: '◐', label: 'In progress' },
  failed: { glyph: '✕', label: 'Failed' },
  attention: { glyph: '!', label: 'Needs review' },
  pending: { glyph: '', label: 'Not reached' },
  discarded: { glyph: '–', label: 'Discarded' },
}

type StepItem = { key: string; state: StepState; title: string; description: ReactNode; meta?: string; children?: ReactNode }

/**
 * The refresh run timeline (spec UF-R06, UF-R07). Each row has a 24px status
 * circle with a glyph and an accessible state name, a title, a description
 * and a right-aligned duration. Color is never the only signal.
 */
export function StepTimeline({ items }: { items: StepItem[] }) {
  return (
    <ol className={styles.list}>
      {items.map((item) => (
        <li key={item.key} className={styles.row}>
          <span className={[styles.circle, styles[item.state]].join(' ')} role="img" aria-label={CIRCLE[item.state].label}>{CIRCLE[item.state].glyph}</span>
          <div className={styles.text}>
            <span className={[styles.title, item.state === 'failed' ? styles.titleFailed : item.state === 'pending' ? styles.titlePending : ''].join(' ')}>{item.title}</span>
            <span className={styles.description}>{item.description}</span>
            {item.children}
          </div>
          <span className={styles.meta}>{item.meta ?? '—'}</span>
        </li>
      ))}
    </ol>
  )
}

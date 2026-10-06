import type { ReactNode } from 'react'
import styles from './Field.module.css'

type FieldProps = { label: string; hint?: string; error?: string; compact?: boolean; children: ReactNode }

/**
 * A visible label around one form control. Wrapping the control in <label>
 * gives it its accessible name without an id.
 */
export function Field({ label, hint, error, compact = false, children }: FieldProps) {
  return (
    <label className={[styles.field, compact ? styles.compactField : ''].join(' ')}>
      {label}
      {children}
      {hint !== undefined && <span className={styles.hint}>{hint}</span>}
      {error !== undefined && <span className={styles.error}>{error}</span>}
    </label>
  )
}

/** Class names for inputs and selects, so every form control looks the same. */
export const inputClass = styles.input
export const filterInputClass = `${styles.input} ${styles.filter}`

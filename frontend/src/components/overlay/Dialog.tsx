import { useCallback, useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Button } from '../controls/Button'
import styles from './Dialog.module.css'
import { useFocusTrap } from './useFocusTrap'

type ConfirmDialogProps = {
  title: string
  children: ReactNode
  confirmLabel: string
  tone?: 'primary' | 'destructive'
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}

/**
 * The confirmation dialog from the handoff. It traps focus, closes on Escape
 * or a backdrop click, and returns focus to the button that opened it.
 * While `busy`, the command is in flight: both buttons are disabled and
 * Escape does nothing, so the user cannot send a second confirmation.
 */
export function ConfirmDialog({ title, children, confirmLabel, tone = 'primary', busy = false, onConfirm, onCancel }: ConfirmDialogProps) {
  const panel = useRef<HTMLDivElement>(null)
  const titleId = useId()
  const cancel = useCallback(() => {
    if (!busy) onCancel()
  }, [busy, onCancel])
  useFocusTrap(panel, true, cancel)

  return createPortal(
    <div
      className={styles.backdrop}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) cancel()
      }}
    >
      <div ref={panel} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1} className={styles.panel}>
        <h2 id={titleId} className={styles.title}>
          {title}
        </h2>
        <div className={styles.body}>{children}</div>
        <div className={styles.actions}>
          <Button onClick={cancel} disabled={busy}>
            Cancel
          </Button>
          <Button variant={tone === 'primary' ? 'primary' : 'destructiveSolid'} onClick={onConfirm} disabled={busy}>
            {busy ? 'Sending…' : confirmLabel}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  )
}

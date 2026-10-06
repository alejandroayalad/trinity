import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import styles from './Toast.module.css'

const ToastContext = createContext<(message: string) => void>(() => undefined)

/**
 * Show one short confirmation at a time, for example after a command.
 * The region has role="status", so screen readers announce each message.
 * A message disappears after 4.2 seconds, as in the handoff.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<{ text: string; id: number } | null>(null)
  const show = useCallback((text: string) => setMessage({ text, id: Date.now() }), [])

  useEffect(() => {
    if (message === null) return
    const timer = window.setTimeout(() => setMessage(null), 4200)
    return () => window.clearTimeout(timer)
  }, [message])

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div role="status" aria-live="polite" className={styles.region}>
        {message !== null && (
          <div key={message.id} className={styles.toast}>
            {message.text}
          </div>
        )}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): (message: string) => void {
  return useContext(ToastContext)
}

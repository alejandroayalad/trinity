import { useEffect, useState } from 'react'
import { shortId } from '../../lib/ids'
import styles from './ShortId.module.css'

/**
 * Show the first 8 characters of an ID in mono (spec R21). The tooltip has
 * the full value, and a click copies it. A screen reader hears the full ID.
 */
export function ShortId({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!copied) return
    const timer = window.setTimeout(() => setCopied(false), 1500)
    return () => window.clearTimeout(timer)
  }, [copied])

  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
    } catch {
      // Clipboard access can be refused. The tooltip still shows the full value.
    }
  }

  return (
    <button type="button" className={styles.shortId} title={value} aria-label={`Copy ID ${value}`} onClick={() => void copy()}>
      {shortId(value)}
      <span className="sr-only" role="status">
        {copied ? 'Copied' : ''}
      </span>
    </button>
  )
}

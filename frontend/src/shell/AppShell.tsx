import { useCallback, useRef, useState } from 'react'
import { Outlet } from 'react-router'
import { useFocusTrap } from '../components/overlay/useFocusTrap'
import { ContextBar } from './ContextBar'
import { Sidebar } from './Sidebar'
import styles from './AppShell.module.css'

/**
 * The small-screen navigation. It mounts only while open, traps focus,
 * closes on Escape or a backdrop press, and returns focus to "☰ Menu".
 */
function Drawer({ close }: { close: () => void }) {
  const panel = useRef<HTMLDivElement>(null)
  useFocusTrap(panel, true, close)
  return (
    <div className={styles.backdrop} onMouseDown={(e) => { if (e.currentTarget === e.target) close() }}>
      <div ref={panel} className={[styles.sidebar, styles.drawer].join(' ')} role="dialog" aria-modal="true" aria-label="Navigation" tabIndex={-1}>
        <Sidebar close={close} />
      </div>
    </div>
  )
}

/**
 * The application frame: a 224px sidebar on the page background, a white
 * workspace with the sticky context bar, and the current page. Below 960px
 * the pinned sidebar hides and the drawer replaces it.
 */
export function AppShell() {
  const [drawer, setDrawer] = useState(false)
  const close = useCallback(() => setDrawer(false), [])
  return (
    <div className={styles.shell}>
      <aside className={[styles.sidebar, styles.pinned].join(' ')}><Sidebar close={close} /></aside>
      {drawer && <Drawer close={close} />}
      <div className={styles.workspace}>
        <ContextBar onMenu={() => setDrawer(true)} />
        <main className={[styles.content, 'page-enter'].join(' ')}><Outlet /></main>
      </div>
    </div>
  )
}

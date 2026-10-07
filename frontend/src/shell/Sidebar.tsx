import { NavLink, useLocation } from 'react-router'
import type { MeResponse } from '../api/types'
import { useSession } from '../session/SessionProvider'
import { navigation } from '../session/capabilities'
import { Button } from '../components/controls/Button'
import { BrandLockup } from '../components/brand/BrandLockup'
import { ROLE_LABELS } from '../lib/copy'
import styles from './AppShell.module.css'

/**
 * Count the runs that wait for Admin review. `/me` reports only the one
 * active run, and A16 allows one refresh lifecycle at a time, so the count
 * is 0 or 1. The value is as fresh as the last `/me` read.
 */
export function awaitingReviewCount(me: MeResponse | null): number {
  return me?.admin_context?.active_run?.status === 'awaiting_approval' ? 1 : 0
}

/**
 * The sidebar content: logo, main and Administration navigation, and the
 * account block. The pinned sidebar and the small-screen drawer both render
 * it. `close` closes the drawer after a navigation click.
 */
export function Sidebar({ close }: { close: () => void }) {
  const { me, signOut } = useSession()
  const { pathname } = useLocation()
  const items = navigation.filter((item) => me?.capabilities.includes(item.capability))
  const count = awaitingReviewCount(me)
  // NavLink marks only an exact or nested route as current. The table view
  // lives under /catalog and run detail under /refresh, so both stay current.
  const link = (item: (typeof items)[number]) => (
    <NavLink key={item.to} to={item.to} onClick={close} className={({ isActive }) => [styles.navItem, isActive || pathname.startsWith(`${item.to}/`) ? styles.current : ''].join(' ')}>
      <span>{item.label}</span>
      {item.to === '/refresh' && count > 0 && <span className={styles.count}>{count}<span className="sr-only"> run awaiting review</span></span>}
    </NavLink>
  )
  const admin = items.filter((item) => item.group === 'admin')
  const initial = (me?.user_id ?? '?').slice(0, 1).toUpperCase()
  return (
    <>
      <div className={styles.brand}><BrandLockup size="nav" /></div>
      <nav aria-label="Main navigation" className={styles.nav}>
        {items.filter((item) => item.group === 'main').map(link)}
        {admin.length > 0 && <span className={styles.group}>Administration</span>}
        {admin.map(link)}
      </nav>
      <div className={styles.spacer} />
      {me && (
        <div className={styles.account}>
          <span className={styles.avatar} aria-hidden="true">{initial}</span>
          <span className={styles.identity}>
            <span className={styles.user} title={me.user_id}>{me.user_id}</span>
            <span className={styles.role}>{ROLE_LABELS[me.role]}</span>
          </span>
          <Button size="small" onClick={() => { void signOut() }}>Sign out</Button>
        </div>
      )}
    </>
  )
}

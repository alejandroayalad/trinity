import { Link, useLocation } from 'react-router'
import { useSession } from '../session/SessionProvider'
import { ShortId } from '../components/controls/ShortId'
import { StatusBadge } from '../components/feedback/StatusBadge'
import { formatDay, formatUtcTime } from '../lib/dates'
import { shortId } from '../lib/ids'
import styles from './AppShell.module.css'

/**
 * The sticky bar above every page. It names the active publication with its
 * three separate dates (spec R14, R20) and, for Admin, links to a run that
 * waits for review. The menu button opens the drawer below 960px.
 */
export function ContextBar({ onMenu }: { onMenu: () => void }) {
  const { me } = useSession()
  const { pathname } = useLocation()
  const publication = me?.publication
  const run = me?.admin_context?.active_run
  const reviewPath = run ? `/refresh/${run.run_id}` : ''
  return (
    <header className={styles.contextBar}>
      <button type="button" className={styles.menuButton} onClick={onMenu}>☰ Menu</button>
      {publication ? (
        <div className={styles.meta}>
          <span>Publication <span className={styles.value}><ShortId value={publication.version_id} /></span></span>
          <span>Published <span className={styles.value}>{formatUtcTime(publication.published_at)}</span></span>
          <span>Latest observation <span className={styles.value}>{formatDay(publication.latest_observation_date)}</span></span>
          <StatusBadge tone="success" glyph="●">Ready</StatusBadge>
        </div>
      ) : (
        <div className={styles.meta}>
          <span>No publication yet</span>
          <StatusBadge tone="neutral" glyph="○">Unavailable</StatusBadge>
        </div>
      )}
      <span className={styles.barSpacer} />
      {/* A button inside a link is invalid, so the pill uses plain short-ID text. */}
      {run?.status === 'awaiting_approval' && pathname !== reviewPath && (
        <Link to={reviewPath} className={styles.reviewPill}>! Run {shortId(run.run_id)} awaits review</Link>
      )}
    </header>
  )
}

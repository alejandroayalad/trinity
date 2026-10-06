import { useCallback, useRef, useState } from 'react'
import { NavLink, Outlet } from 'react-router'
import { useSession } from '../session/SessionProvider'
import { navigation } from '../session/capabilities'
import { Button, ButtonLink } from '../components/controls/Button'
import { ShortId } from '../components/controls/ShortId'
import { useFocusTrap } from '../components/overlay/useFocusTrap'
import { formatUtcTime } from '../lib/dates'

function Sidebar({ close }: { close: () => void }) {
  const { me, signOut } = useSession()
  return <><img src="/brand/wordmark.png" alt="Trinity" className="wordmark" />
    <nav aria-label="Main navigation">{navigation.filter((item) => me?.capabilities.includes(item.capability)).map((item) => <NavLink key={item.to} to={item.to} onClick={close}>{item.label}</NavLink>)}</nav>
    <div className="account"><span>{me?.user_id}</span><span className="muted">{me?.role}</span><Button onClick={() => { void signOut() }}>Sign out</Button></div></>
}
function Drawer({ close }: { close: () => void }) {
  const panel = useRef<HTMLDivElement>(null)
  useFocusTrap(panel, true, close)
  return <div className="drawer-backdrop" onMouseDown={(e) => { if (e.currentTarget === e.target) close() }}><div ref={panel} className="sidebar drawer" role="dialog" aria-modal="true" aria-label="Navigation" tabIndex={-1}><Button onClick={close}>Close menu</Button><Sidebar close={close} /></div></div>
}
export function AppShell() {
  const { me } = useSession()
  const [drawer, setDrawer] = useState(false)
  const close = useCallback(() => setDrawer(false), [])
  const publication = me?.publication
  const run = me?.admin_context?.active_run
  return <div className="app-shell"><aside className="sidebar pinned"><Sidebar close={close} /></aside>
    {drawer && <Drawer close={close} />}
    <div className="workspace"><header className="context-bar"><Button className="menu-button" onClick={() => setDrawer(true)}>☰ Menu</Button>
      {publication ? <><ShortId value={publication.version_id} /><span>{formatUtcTime(publication.published_at)}</span><span>Latest observation: {publication.latest_observation_date}</span><span className="ready">● Ready</span></> : <span>No publication yet · ○ Unavailable</span>}
      {run?.status === 'awaiting_approval' && <ButtonLink to={`/refresh/${run.run_id}`}>Awaiting review</ButtonLink>}
    </header><main className="content page-enter"><Outlet /></main></div></div>
}

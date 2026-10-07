import { Navigate, Outlet } from 'react-router'
import type { Capability, LandingScreen } from '../api/types'
import { useSession } from './SessionProvider'
import { PageError } from '../pages/shared'
import { LoadingRows } from '../components/feedback/States'

/**
 * Sidebar items. `main` items are for every role that has the capability;
 * `admin` items appear under the "Administration" group label.
 */
export const navigation: { to: string; label: string; capability: Capability; group: 'main' | 'admin' }[] = [
  { to: '/dashboard', label: 'Dashboard', capability: 'national:read', group: 'main' },
  { to: '/catalog', label: 'Catalog', capability: 'preview:detail', group: 'main' },
  { to: '/sql', label: 'SQL Explorer', capability: 'sql:execute', group: 'main' },
  { to: '/refresh', label: 'Refresh', capability: 'refresh:read', group: 'admin' },
  { to: '/settings', label: 'Settings', capability: 'settings:read', group: 'admin' },
]
export const landingPath = (screen: LandingScreen) => ({ waiting: '/waiting', setup: '/setup', refresh_runs: '/refresh', national_dashboard: '/dashboard', explorer: '/dashboard' })[screen]

/** Do not mount a denied page: its query hooks must never send a request. */
export function RequireCapability({ capability }: { capability?: Capability }) {
  const { me, loading, error, retryStartup } = useSession()
  if (loading) return <LoadingRows />
  if (error) return <PageError error={error} onRetry={retryStartup} />
  if (!me) return <Navigate to="/sign-in" replace />
  if (capability && !me.capabilities.includes(capability)) return <Navigate to={landingPath(me.landing_screen)} replace />
  return <Outlet />
}
export function Landing() {
  const { me } = useSession()
  return <Navigate to={me ? landingPath(me.landing_screen) : '/sign-in'} replace />
}

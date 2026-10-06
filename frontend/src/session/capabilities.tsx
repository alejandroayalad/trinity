import { Navigate, Outlet } from 'react-router'
import type { Capability, LandingScreen } from '../api/types'
import { useSession } from './SessionProvider'
import { PageError } from '../pages/shared'
import { LoadingRows } from '../components/feedback/States'

export const navigation: { to: string; label: string; capability: Capability }[] = [
  { to: '/dashboard', label: 'Overview', capability: 'national:read' },
  { to: '/catalog', label: 'Catalog', capability: 'preview:detail' },
  { to: '/sql', label: 'SQL Explorer', capability: 'sql:execute' },
  { to: '/refresh', label: 'Refresh', capability: 'refresh:read' },
  { to: '/settings', label: 'Schedule', capability: 'settings:read' },
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

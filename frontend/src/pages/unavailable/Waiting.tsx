import { useSession } from '../../session/SessionProvider'
import { NothingToShow } from '../../components/feedback/States'
import { ButtonLink } from '../../components/controls/Button'
export function Waiting() {
  const { me } = useSession()
  return <NothingToShow action={me?.capabilities.includes('refresh:read') ? <ButtonLink to="/refresh" variant="primary">Go to Refresh</ButtonLink> : undefined} />
}

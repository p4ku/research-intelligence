import { getSessionUser } from '@/lib/auth/session'
import { getFeatures } from '@/lib/features-server'
import { getT } from '@/lib/i18n-server'
import { getWorkspacesState } from '@/lib/workspace-server'
import { runnableWorkspaces } from '../runs/stoppable'
import { DashboardSkeleton } from './skeletons'

/**
 * Instant loading state for the dashboard: the real header (name from the
 * session cookie — no backend call) over the ledger skeleton, matching the
 * page's own Suspense fallback pixel for pixel.
 */
export default async function Loading() {
  const [user, state, t, features] = await Promise.all([
    getSessionUser(),
    getWorkspacesState(),
    getT(),
    getFeatures(),
  ])
  const name = user?.name.split(' ')[0] || t('there')
  const showCard = state.kind === 'ok' ? runnableWorkspaces(state).size > 0 : true
  return <DashboardSkeleton t={t} name={name} features={features} showCard={showCard} />
}

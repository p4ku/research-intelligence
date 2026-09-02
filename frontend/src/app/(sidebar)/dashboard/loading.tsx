import { getSessionUser } from '@/lib/auth/session'
import { getT } from '@/lib/i18n-server'
import { DashboardSkeleton } from './skeletons'

/**
 * Instant loading state for the dashboard: the real header (name from the
 * session cookie — no backend call) over the three section skeletons, matching
 * the page's own Suspense fallbacks pixel for pixel.
 */
export default async function Loading() {
  const [user, t] = await Promise.all([getSessionUser(), getT()])
  const name = user?.name.split(' ')[0] || t('there')
  return <DashboardSkeleton t={t} name={name} />
}

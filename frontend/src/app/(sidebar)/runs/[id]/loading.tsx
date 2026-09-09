import { getT } from '@/lib/i18n-server'
import { RunPageSkeleton } from './skeletons'

/**
 * Instant loading state for a run: crumbs, header, band, facts and timeline
 * as skeletons, matching the page's own Suspense fallbacks. loading.tsx gets
 * no params, so the run id in the crumb and title is a bone here.
 */
export default async function Loading() {
  return <RunPageSkeleton t={await getT()} />
}

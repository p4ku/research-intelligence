import { getT } from '@/lib/i18n-server'
import { BriefingPageSkeleton } from './skeletons'

/** Instant loading state for the archive, matching the page's own Suspense fallback. */
export default async function Loading() {
  const t = await getT()
  return <BriefingPageSkeleton t={t} />
}

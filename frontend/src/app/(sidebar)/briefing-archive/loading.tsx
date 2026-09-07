import { getFeatures } from '@/lib/features-server'
import { getT } from '@/lib/i18n-server'
import { BriefingPageSkeleton } from './skeletons'

/** Instant loading state for the archive, matching the page's own Suspense fallback. */
export default async function Loading() {
  const [t, features] = await Promise.all([getT(), getFeatures()])
  return <BriefingPageSkeleton t={t} features={features} />
}

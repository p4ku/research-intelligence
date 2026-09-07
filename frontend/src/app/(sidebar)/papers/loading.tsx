import { getFeatures } from '@/lib/features-server'
import { getT } from '@/lib/i18n-server'
import { PapersSkeleton } from './skeletons'

/**
 * Instant loading state for the papers browser: the real header over the
 * browser skeleton, matching the page's own Suspense fallback pixel for pixel.
 * With the `all_papers` demo flag off the page 404s, so nothing paints first.
 */
export default async function Loading() {
  const [t, features] = await Promise.all([getT(), getFeatures()])
  if (!features.all_papers) return null
  return <PapersSkeleton t={t} />
}

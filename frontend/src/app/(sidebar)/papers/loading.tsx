import { getT } from '@/lib/i18n-server'
import { PapersSkeleton } from './skeletons'

/**
 * Instant loading state for the papers browser: the real header over the
 * browser skeleton, matching the page's own Suspense fallback pixel for pixel.
 */
export default async function Loading() {
  const t = await getT()
  return <PapersSkeleton t={t} />
}

import { getT } from '@/lib/i18n-server'
import { AskPageSkeleton } from './skeletons'

/**
 * Instant loading state for the assistant: the real header and console
 * chrome, bones for the picker and the history, matching the page's own
 * Suspense fallback.
 */
export default async function Loading() {
  const t = await getT()
  return <AskPageSkeleton t={t} />
}

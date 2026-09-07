import { hasFeature } from '@/lib/features-server'
import { getT } from '@/lib/i18n-server'
import { AskPageSkeleton } from './skeletons'

/**
 * Instant loading state for the assistant: the real header and console
 * chrome, bones for the picker and the history, matching the page's own
 * Suspense fallback.
 *
 * With the `ask` demo flag off the page calls notFound(), and this file is
 * what Next paints first — so it renders nothing rather than the console
 * skeleton of a route that is about to answer the not-found card. The file
 * itself stays: loading-convention.test.ts requires a sibling loading.tsx for
 * every force-dynamic page, and the flag is reversible.
 */
export default async function Loading() {
  if (!(await hasFeature('ask'))) return null
  const t = await getT()
  return <AskPageSkeleton t={t} />
}

import { getT } from '@/lib/i18n-server'
import { PaperPageSkeleton } from './skeletons'

/**
 * Instant loading state for a paper: crumbs and the record skeleton, matching
 * the page's own Suspense fallback. loading.tsx gets no params, so the title
 * crumb is a bone here.
 */
export default async function Loading() {
  const t = await getT()
  return <PaperPageSkeleton t={t} />
}

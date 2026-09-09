import { getT } from '@/lib/i18n-server'
import { RunsPageSkeleton } from './skeletons'

/**
 * Instant loading state for the runs list: the header over the section
 * skeleton the page itself uses as its Suspense fallback. Nothing to await but
 * the language — the header copy is static and the shell needs no session data.
 */
export default async function Loading() {
  return <RunsPageSkeleton t={await getT()} />
}

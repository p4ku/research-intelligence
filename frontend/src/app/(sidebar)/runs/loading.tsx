import { RunsPageSkeleton } from './skeletons'

/**
 * Instant loading state for the runs list: the header over the section
 * skeleton the page itself uses as its Suspense fallback. Nothing to await —
 * the header copy is static and the shell needs no session data.
 */
export default function Loading() {
  return <RunsPageSkeleton />
}

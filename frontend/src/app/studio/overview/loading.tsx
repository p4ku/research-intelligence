import { OverviewSkeleton } from './skeletons'

/**
 * The navigation shell: the same skeleton the page uses as its Suspense
 * fallback, so nothing jumps when the section arrives.
 */
export default function OverviewLoading() {
  return <OverviewSkeleton />
}

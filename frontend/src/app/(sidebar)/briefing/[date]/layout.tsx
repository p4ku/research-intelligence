import { notFound } from 'next/navigation'
import { isEditionDate } from '../format'

/**
 * The permalink's shape guard, and nothing else.
 *
 * It lives in a layout because a layout renders *above* the segment's
 * `loading.tsx` boundary: `notFound()` from inside the page would arrive
 * after the shell had already been streamed with HTTP 200 (see the pass-2
 * note in docs/skeletons.md). Here `/briefing/not-a-date` is a plain 404
 * again, for this segment and for `run/` below it.
 */
export default async function BriefingEditionLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ date: string }>
}) {
  const { date } = await params
  if (!isEditionDate(date)) notFound()
  return children
}

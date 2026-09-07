import { bff } from '@/lib/bff/core/handler'
import { trustCorpusFor } from '@/lib/bff/corpus/snapshot'
import { toPalette } from '@/lib/bff/papers/palette'
import { paletteQuery } from '@/lib/bff/papers/schema'
import { papers } from '@/lib/bff/papers/service'

export const dynamic = 'force-dynamic'

/** The picker may open on a corpus confirmed this recently without asking Django again. */
const PICKER_TRUST_MS = 10_000

/**
 * The Ask picker's corpus: every paper the user can see, slimmed to what a
 * row shows. Scored from the per-user corpus snapshot, so the console can
 * ask for it the moment it has painted, and again on every visit for pennies.
 *
 * A request marked `retry=1` is the client's one automatic second attempt;
 * it is logged with the problem the first attempt ended in, so a blip that
 * healed itself still leaves a trace to investigate. The marker is only a
 * marker: one that fails to parse is ignored, and the papers are served.
 */
export const GET = bff('papers', async (request) => {
  const marker = paletteQuery.safeParse(Object.fromEntries(request.nextUrl.searchParams))
  if (marker.success && marker.data.retry) {
    console.warn(`[bff] palette retried by the client after: ${marker.data.after || 'unknown'}`)
  }
  trustCorpusFor(PICKER_TRUST_MS)
  return Response.json(toPalette(await papers.listEverywhere()))
})

import { bff } from '@/lib/bff/core/handler'
import { recentCorpus } from '@/lib/bff/papers/corpus'
import { toPalette } from '@/lib/bff/papers/palette'
import { paletteQuery } from '@/lib/bff/papers/schema'

export const dynamic = 'force-dynamic'

/**
 * The Ask picker's corpus: every paper the user can see, slimmed to what a
 * row shows. Served from the short per-user cache, so the console can ask
 * for it the moment it has painted, and again on every visit for pennies.
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
  return Response.json(toPalette(await recentCorpus()))
})

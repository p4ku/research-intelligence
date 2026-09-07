import { bff } from '@/lib/bff/core/handler'
import { toPalette } from '@/lib/bff/papers/palette'
import { papers } from '@/lib/bff/papers/service'

export const dynamic = 'force-dynamic'

/**
 * The Ask picker's corpus: every paper the user can see, slimmed to what a
 * row shows. Scored from the per-user corpus snapshot, so the console can
 * ask for it the moment it has painted, and again on every visit for pennies.
 */
export const GET = bff('papers', async () =>
  Response.json(toPalette(await papers.listEverywhere())),
)

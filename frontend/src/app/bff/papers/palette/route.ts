import { bff } from '@/lib/bff/core/handler'
import { recentCorpus } from '@/lib/bff/papers/corpus'
import { toPalette } from '@/lib/bff/papers/palette'

export const dynamic = 'force-dynamic'

/**
 * The Ask picker's corpus: every paper the user can see, slimmed to what a
 * row shows. Served from the short per-user cache, so the console can ask
 * for it the moment it has painted, and again on every visit for pennies.
 */
export const GET = bff('papers', async () => Response.json(toPalette(await recentCorpus())))

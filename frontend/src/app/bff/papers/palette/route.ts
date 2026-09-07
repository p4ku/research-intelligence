import { bff } from '@/lib/bff/core/handler'
import { parseQuery } from '@/lib/bff/core/validate'
import { trustCorpusFor } from '@/lib/bff/corpus/snapshot'
import { toPalette } from '@/lib/bff/papers/palette'
import { paletteQuery } from '@/lib/bff/papers/schema'
import { papers } from '@/lib/bff/papers/service'

export const dynamic = 'force-dynamic'

/** The picker may open on a corpus confirmed this recently without asking Django again. */
const PICKER_TRUST_MS = 10_000

/**
 * The Ask picker's rows: the papers the reader's text matches, slimmed to
 * what a row shows and cut at `limit`. Scored from the per-user corpus
 * snapshot, so the console can ask on every keystroke for pennies and never
 * holds more than a screenful.
 */
export const GET = bff('papers', async (request) => {
  trustCorpusFor(PICKER_TRUST_MS)
  const query = parseQuery(paletteQuery, request.nextUrl)
  return Response.json(toPalette(await papers.listEverywhere(), query))
})

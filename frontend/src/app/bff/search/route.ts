import { bff } from '@/lib/bff/core/handler'
import { parseQuery } from '@/lib/bff/core/validate'
import { trustCorpusFor } from '@/lib/bff/corpus/snapshot'
import { searchQuery } from '@/lib/bff/search/schema'
import { search } from '@/lib/bff/search/service'

export const dynamic = 'force-dynamic'

/** A keystroke may search a corpus confirmed this recently without asking Django again. */
const TYPING_TRUST_MS = 10_000

export const GET = bff('search', async (request) => {
  trustCorpusFor(TYPING_TRUST_MS)
  return Response.json(await search.run(parseQuery(searchQuery, request.nextUrl)))
})

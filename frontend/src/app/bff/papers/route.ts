import { bff } from '@/lib/bff/core/handler'
import { parseQuery } from '@/lib/bff/core/validate'
import { trustCorpusFor } from '@/lib/bff/corpus/snapshot'
import { papersQuery } from '@/lib/bff/papers/schema'
import { papers } from '@/lib/bff/papers/service'

export const dynamic = 'force-dynamic'

/** A filter click may read a corpus confirmed this recently without asking Django again. */
const PAGE_TRUST_MS = 10_000

export const GET = bff('papers', async (request) => {
  trustCorpusFor(PAGE_TRUST_MS)
  return Response.json(await papers.list(parseQuery(papersQuery, request.nextUrl)))
})

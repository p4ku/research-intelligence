import { editionQuery } from '@/lib/bff/briefings/schema'
import { assertDate, briefings } from '@/lib/bff/briefings/service'
import { bff } from '@/lib/bff/core/handler'
import { problem } from '@/lib/bff/core/problem'
import { parseQuery } from '@/lib/bff/core/validate'
import { getLang } from '@/lib/i18n-server'

export const dynamic = 'force-dynamic'

export const GET = bff('briefings', async (request, ctx) => {
  const { date } = await ctx.params
  // `?workspace_id=` and `?run_id=` left empty mean "not given" — every
  // domain, the day's newest — not a malformed id. Other values stay, so a
  // repeated key still reads as its last non-empty value.
  const url = new URL(request.nextUrl)
  const kept = new URLSearchParams()
  for (const [key, value] of request.nextUrl.searchParams) if (value !== '') kept.append(key, value)
  url.search = kept.toString()
  const { workspace_id, run_id, scope, page, page_size, min_score, score, sort, ordering } =
    parseQuery(editionQuery, url)
  const minScore = min_score ?? score
  const sortParam = sort ?? ordering

  const dimensionFilters: Record<string, number> = {}
  for (const [k, v] of request.nextUrl.searchParams) {
    if (!v || v.trim() === '') continue
    const num = Number(v)
    if (isNaN(num) || num <= 0) continue

    let dimKey: string | null = null
    if (k.startsWith('dim_min:')) dimKey = k.slice(8)
    else if (k.startsWith('min_dim:')) dimKey = k.slice(8)
    else if (k.startsWith('dim:')) dimKey = k.slice(4)
    else if (k.startsWith('min_') && k !== 'min_score' && k !== 'min_date' && k !== 'min_created_at') {
      dimKey = k.slice(4)
    }

    if (dimKey) {
      dimensionFilters[dimKey.trim().toLowerCase()] = num
    }
  }

  const found = await briefings.findByDate(
    assertDate(date),
    await getLang(),
    workspace_id,
    run_id,
    scope,
    page,
    page_size,
    minScore,
    sortParam,
    dimensionFilters,
  )
  if (!found) throw problem('not-found', { detail: 'No briefing for that day.' })
  return Response.json(found)
})

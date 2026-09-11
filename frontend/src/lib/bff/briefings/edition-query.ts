import type { NextRequest } from 'next/server'
import { parseQuery } from '../core/validate'
import { editionQuery } from './schema'

/**
 * The edition a BFF request names. `?workspace_id=` and `?run_id=` left
 * empty mean "not given" — every domain, the day's newest — not a malformed
 * id. Other values stay, so a repeated key still reads as its last non-empty
 * value. Shared by the JSON route and the PDF export.
 */
export function editionQueryOf(request: NextRequest) {
  const url = new URL(request.nextUrl)
  const kept = new URLSearchParams()
  for (const [key, value] of request.nextUrl.searchParams) if (value !== '') kept.append(key, value)
  url.search = kept.toString()
  return parseQuery(editionQuery, url)
}

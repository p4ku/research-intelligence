/**
 * The list envelope every BFF (and every requested Django) list endpoint
 * uses: DRF's page-number shape, `{count, next, previous, results}`.
 * Pure — the contract scripts import this.
 */
import * as z from 'zod'

export const listQuery = z.object({
  page: z.coerce.number().int().min(1).catch(1).default(1),
  page_size: z.coerce.number().int().min(1).max(200).catch(50).default(50),
})
export type ListQuery = z.infer<typeof listQuery>

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export function pageSchema<T extends z.ZodType>(item: T) {
  return z.object({
    count: z.number().int().min(0),
    next: z.string().nullable(),
    previous: z.string().nullable(),
    results: z.array(item),
  })
}

/**
 * Paginate an in-memory list (the `composed`/`stub` sources hold the full
 * corpus anyway). `next`/`previous` are BFF-relative URLs — Django-internal
 * URLs must never leak to the browser.
 */
export function paginate<T>(
  items: readonly T[],
  query: ListQuery,
  basePath: string,
  extraParams: Record<string, string> = {},
): Page<T> {
  const { page, page_size } = query
  const start = (page - 1) * page_size
  const results = items.slice(start, start + page_size)
  const pageUrl = (n: number) => {
    const params = new URLSearchParams(extraParams)
    if (n > 1) params.set('page', String(n))
    params.set('page_size', String(page_size))
    return `${basePath}?${params.toString()}`
  }
  return {
    count: items.length,
    next: start + page_size < items.length ? pageUrl(page + 1) : null,
    previous: page > 1 ? pageUrl(page - 1) : null,
    results,
  }
}

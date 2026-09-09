import { describe, expect, test } from 'bun:test'
import type { FetchedPage } from '../core/drain'
import type { Page } from '../core/pagination'
import { drainScored } from './scored'

interface Row {
  id: string
  workspace_id: string
}

/** Domains of `n` rows each, served newest-first in pages, every read recorded. */
function upstream(sizes: Record<string, number>) {
  const rows = new Map<string, Row[]>()
  for (const [ws, n] of Object.entries(sizes)) {
    rows.set(
      ws,
      Array.from({ length: n }, (_, i) => ({ id: `${ws}-${n - i}`, workspace_id: ws })),
    )
  }
  const reads: Array<[string, number, number]> = []
  const fetchPage = async (
    ws: string,
    page: number,
    pageSize: number,
  ): Promise<FetchedPage<Row>> => {
    reads.push([ws, page, pageSize])
    const all = rows.get(ws) ?? []
    const start = (page - 1) * pageSize
    const results = all.slice(start, start + pageSize)
    const body: Page<Row> = {
      count: all.length,
      next: start + pageSize < all.length ? `?page=${page + 1}` : null,
      previous: page > 1 ? `?page=${page - 1}` : null,
      results,
    }
    return { page: body, bytes: JSON.stringify(body).length }
  }
  return { rows, reads, fetchPage }
}

describe('drainScored', () => {
  test('under the cap every domain is read to its end, in the order given', async () => {
    const { rows, reads, fetchPage } = upstream({ a: 3, b: 5 })
    const out = await drainScored(['a', 'b'], fetchPage, { pageSize: 2, cap: 100 })
    expect([...out.byWorkspace.keys()]).toEqual(['a', 'b'])
    expect(out.byWorkspace.get('a')).toEqual(rows.get('a'))
    expect(out.byWorkspace.get('b')).toEqual(rows.get('b'))
    expect(out.truncated).toBeUndefined()
    expect(reads.map(([ws, page]) => `${ws}${page}`)).toEqual(['a1', 'a2', 'b1', 'b2', 'b3'])
    expect(out.bytes).toBeGreaterThan(0)
  })

  test('the cap is shared: later domains get what is left, past it only the size is read', async () => {
    const { reads, fetchPage } = upstream({ a: 5, b: 5, c: 4 })
    const out = await drainScored(['a', 'b', 'c'], fetchPage, { pageSize: 2, cap: 7 })
    expect(out.byWorkspace.get('a')?.map((r) => r.id)).toEqual(['a-5', 'a-4', 'a-3', 'a-2', 'a-1'])
    // The newest two of b, read as one page of two — not a page of two hundred.
    expect(out.byWorkspace.get('b')?.map((r) => r.id)).toEqual(['b-5', 'b-4'])
    expect(reads.filter(([ws]) => ws === 'b')).toEqual([['b', 1, 2]])
    // c is past the cap: one row asked for, none kept, its size still counted.
    expect(out.byWorkspace.get('c')).toEqual([])
    expect(reads.filter(([ws]) => ws === 'c')).toEqual([['c', 1, 1]])
    expect(out.truncated).toEqual({ kept: 7, total: 14 })
  })

  test('a domain with no papers keeps an empty list and no truncation', async () => {
    const { fetchPage } = upstream({ a: 0, b: 2 })
    const out = await drainScored(['a', 'b'], fetchPage, { pageSize: 200, cap: 2000 })
    expect(out.byWorkspace.get('a')).toEqual([])
    expect(out.byWorkspace.get('b')?.length).toBe(2)
    expect(out.truncated).toBeUndefined()
  })

  test('no memberships is an empty corpus with nothing read', async () => {
    const { reads, fetchPage } = upstream({})
    const out = await drainScored([], fetchPage, { pageSize: 200, cap: 2000 })
    expect(out.byWorkspace.size).toBe(0)
    expect(out.bytes).toBe(0)
    expect(reads).toEqual([])
  })

  test('exactly the cap, with nothing beyond it, is not a truncation', async () => {
    const { fetchPage } = upstream({ a: 3, b: 2 })
    const out = await drainScored(['a', 'b'], fetchPage, { pageSize: 2, cap: 5 })
    expect(out.truncated).toBeUndefined()
  })
})

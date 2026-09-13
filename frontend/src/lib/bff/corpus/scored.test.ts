import { describe, expect, test } from 'bun:test'
import type { FetchedPage } from '../core/drain'
import type { Page } from '../core/pagination'
import { drainScored } from './scored'

interface Row {
  id: string
  workspace_id: string
  created_at: string
}

/** Rows numbered n..1 per domain, newest first, `created_at` = start minus the row's position in seconds. */
function domain(ws: string, n: number, start = 1_000): Row[] {
  return Array.from({ length: n }, (_, i) => ({
    id: `${ws}-${n - i}`,
    workspace_id: ws,
    created_at: new Date(Date.UTC(2026, 8, 1, 0, 0, start - i)).toISOString(),
  }))
}

/** Domains served newest-first in pages, every read recorded; `bytes` = one per row plus one per page. */
function upstream(rows: Map<string, Row[]>) {
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
    return { page: body, bytes: results.length + 1 }
  }
  return { reads, fetchPage }
}

const ids = (rows: Row[] | undefined) => rows?.map((r) => r.id)

describe('drainScored', () => {
  test('under the cap every domain is read to its end and kept in the order given', async () => {
    const rows = new Map([
      ['a', domain('a', 3)],
      ['b', domain('b', 5)],
    ])
    const { reads, fetchPage } = upstream(rows)
    const out = await drainScored(['a', 'b'], fetchPage, { pageSize: 2, cap: 100 })
    expect([...out.byWorkspace.keys()]).toEqual(['a', 'b'])
    expect(out.byWorkspace.get('a')).toEqual(rows.get('a'))
    expect(out.byWorkspace.get('b')).toEqual(rows.get('b'))
    expect(out.truncated).toBeUndefined()
    // The first page of every domain first, then pages only as buffers run dry.
    expect(reads.map(([ws, page]) => `${ws}${page}`)).toEqual(['a1', 'b1', 'a2', 'b2', 'b3'])
    expect(out.bytes).toBe(3 + 5 + reads.length)
  })

  test('the cap keeps the newest papers across domains, not the first domains whole', async () => {
    // a's papers are old, b's are new: the cap must take all of b before any of a.
    const rows = new Map([
      ['a', domain('a', 3, 10)],
      ['b', domain('b', 2, 1_000)],
    ])
    const { fetchPage } = upstream(rows)
    const out = await drainScored(['a', 'b'], fetchPage, { pageSize: 200, cap: 4 })
    expect(ids(out.byWorkspace.get('b'))).toEqual(['b-2', 'b-1'])
    expect(ids(out.byWorkspace.get('a'))).toEqual(['a-3', 'a-2'])
    expect(out.truncated).toEqual({ kept: 4, total: 5 })
  })

  test('a domain whose papers are all older than the cap keeps an empty list and still counts', async () => {
    const rows = new Map([
      ['a', domain('a', 5, 1_000)],
      ['b', domain('b', 4, 10)],
    ])
    const { reads, fetchPage } = upstream(rows)
    const out = await drainScored(['a', 'b'], fetchPage, { pageSize: 2, cap: 3 })
    expect(ids(out.byWorkspace.get('a'))).toEqual(['a-5', 'a-4', 'a-3'])
    expect(out.byWorkspace.get('b')).toEqual([])
    expect(out.truncated).toEqual({ kept: 3, total: 9 })
    // No page is bigger than the cap, and b is read once, for its size and its head.
    expect(reads).toEqual([
      ['a', 1, 2],
      ['b', 1, 2],
      ['a', 2, 2],
    ])
  })

  test('the cap on a page boundary reads no further page', async () => {
    const rows = new Map([['a', domain('a', 4)]])
    const { reads, fetchPage } = upstream(rows)
    const out = await drainScored(['a'], fetchPage, { pageSize: 2, cap: 2 })
    expect(ids(out.byWorkspace.get('a'))).toEqual(['a-4', 'a-3'])
    expect(reads).toEqual([['a', 1, 2]])
    expect(out.truncated).toEqual({ kept: 2, total: 4 })
  })

  test('exactly the cap, with nothing beyond it, is not a truncation', async () => {
    const rows = new Map([
      ['a', domain('a', 3)],
      ['b', domain('b', 2)],
    ])
    const { fetchPage } = upstream(rows)
    const out = await drainScored(['a', 'b'], fetchPage, { pageSize: 2, cap: 5 })
    expect(out.truncated).toBeUndefined()
  })

  test('a domain with no papers keeps an empty list and no truncation', async () => {
    const rows = new Map([
      ['a', []],
      ['b', domain('b', 2)],
    ])
    const { fetchPage } = upstream(rows)
    const out = await drainScored(['a', 'b'], fetchPage, { pageSize: 200, cap: 2000 })
    expect(out.byWorkspace.get('a')).toEqual([])
    expect(out.byWorkspace.get('b')?.length).toBe(2)
    expect(out.truncated).toBeUndefined()
  })

  test('no memberships is an empty corpus with nothing read', async () => {
    const { reads, fetchPage } = upstream(new Map())
    const out = await drainScored([], fetchPage, { pageSize: 200, cap: 2000 })
    expect(out.byWorkspace.size).toBe(0)
    expect(out.bytes).toBe(0)
    expect(reads).toEqual([])
  })

  test('a row that shifts onto a later page is kept once', async () => {
    const all = domain('a', 4)
    const { fetchPage } = upstream(new Map([['a', all]]))
    // A run inserted a row between the two reads: page 2 repeats the last row of page 1.
    const shifting = async (ws: string, page: number, size: number) => {
      const fetched = await fetchPage(ws, page, size)
      if (page === 2) fetched.page.results.unshift(all[1]!)
      return fetched
    }
    const out = await drainScored(['a'], shifting, { pageSize: 2, cap: 100 })
    expect(ids(out.byWorkspace.get('a'))).toEqual(['a-4', 'a-3', 'a-2', 'a-1'])
  })

  test('an empty page that still points at a next page is an upstream-shape problem', async () => {
    const { fetchPage } = upstream(new Map([['a', domain('a', 1)]]))
    const broken = async (ws: string, page: number, size: number) => {
      const fetched = await fetchPage(ws, page, size)
      fetched.page.results = []
      fetched.page.next = '?page=2'
      return fetched
    }
    await expect(drainScored(['a'], broken, { pageSize: 2, cap: 100 })).rejects.toThrow(
      'An empty page 1 of workspace a still pointed at a next page',
    )
  })

  test('one failing page fails the whole corpus', async () => {
    const { fetchPage } = upstream(
      new Map([
        ['a', domain('a', 1)],
        ['b', domain('b', 1)],
      ]),
    )
    const failing = async (ws: string, page: number, size: number) => {
      if (ws === 'b') throw new Error('upstream 502')
      return fetchPage(ws, page, size)
    }
    await expect(drainScored(['a', 'b'], failing, { pageSize: 2, cap: 100 })).rejects.toThrow(
      'upstream 502',
    )
  })
})

import { describe, expect, test } from 'bun:test'
import { drain, type FetchedPage } from './drain'
import type { Page } from './pagination'

interface Row {
  id: string
  at: number
}

/** A newest-first list of `n` rows served in pages, counting the reads. */
function upstream(n: number, { failOn = 0 } = {}) {
  const rows: Row[] = Array.from({ length: n }, (_, i) => ({ id: `r${n - i}`, at: n - i }))
  const reads: number[] = []
  const fetchPage = async (page: number, pageSize: number): Promise<FetchedPage<Row>> => {
    reads.push(page)
    if (page === failOn) throw new Error('boom')
    const start = (page - 1) * pageSize
    const results = rows.slice(start, start + pageSize)
    const body: Page<Row> = {
      count: n,
      next: start + pageSize < n ? `?page=${page + 1}` : null,
      previous: page > 1 ? `?page=${page - 1}` : null,
      results,
    }
    return { page: body, bytes: JSON.stringify(body).length }
  }
  return { rows, reads, fetchPage }
}

const id = (r: Row) => r.id

describe('drain', () => {
  test('a single page is read once and kept whole', async () => {
    const { rows, reads, fetchPage } = upstream(3)
    const out = await drain(fetchPage, { pageSize: 10, maxItems: 100, id })
    expect(out.items).toEqual(rows)
    expect(out.total).toBe(3)
    expect(out.pages).toBe(1)
    expect(reads).toEqual([1])
  })

  test('walks every page when nothing bounds it', async () => {
    const { rows, reads, fetchPage } = upstream(23)
    const out = await drain(fetchPage, { pageSize: 10, maxItems: 100, id })
    expect(out.items).toEqual(rows)
    expect(reads).toEqual([1, 2, 3])
    expect(out.bytes).toBeGreaterThan(0)
  })

  test('the cap keeps the first N and reads only the pages that hold them', async () => {
    const { rows, reads, fetchPage } = upstream(50)
    const out = await drain(fetchPage, { pageSize: 10, maxItems: 25, id })
    expect(out.items).toEqual(rows.slice(0, 25))
    expect(out.total).toBe(50)
    expect(reads).toEqual([1, 2, 3])
  })

  test('a cap on a page boundary does not read the next page', async () => {
    const { reads, fetchPage } = upstream(50)
    const out = await drain(fetchPage, { pageSize: 10, maxItems: 20, id })
    expect(out.items).toHaveLength(20)
    expect(reads).toEqual([1, 2])
  })

  test('`until` stops before the first item it matches and drops the rest', async () => {
    const { rows, reads, fetchPage } = upstream(30)
    const out = await drain(fetchPage, {
      pageSize: 10,
      maxItems: 100,
      id,
      until: (r) => r.at < 17,
    })
    expect(out.items).toEqual(rows.filter((r) => r.at >= 17))
    expect(reads).toEqual([1, 2])
  })

  test('a row that shifts across pages appears once', async () => {
    const { fetchPage } = upstream(15)
    const shifting = async (page: number, size: number) => {
      const got = await fetchPage(page, size)
      // The second page re-serves the last row of the first, as a run inserting
      // a newer row between the two reads would make it do.
      if (page === 2) got.page.results.unshift({ id: 'r6', at: 6 })
      return got
    }
    const out = await drain(shifting, { pageSize: 10, maxItems: 100, id })
    expect(out.items.map((r) => r.id).filter((x) => x === 'r6')).toHaveLength(1)
    expect(out.items).toHaveLength(15)
  })

  test('a failing page fails the whole drain', async () => {
    const { fetchPage } = upstream(30, { failOn: 2 })
    await expect(drain(fetchPage, { pageSize: 10, maxItems: 100, id })).rejects.toThrow('boom')
  })

  test('an empty page that still points at a next page is an upstream-shape problem', async () => {
    const stuck = async (): Promise<FetchedPage<Row>> => ({
      page: { count: 5, next: '?page=2', previous: null, results: [] },
      bytes: 10,
    })
    await expect(drain(stuck, { pageSize: 10, maxItems: 100, id })).rejects.toMatchObject({
      problem: { type: '/problems/upstream-shape' },
    })
  })

  test('bytes sum over the pages read', async () => {
    const sized = async (page: number): Promise<FetchedPage<Row>> => ({
      page: {
        count: 2,
        next: page === 1 ? '?page=2' : null,
        previous: null,
        results: [{ id: `r${page}`, at: page }],
      },
      bytes: 100 * page,
    })
    const out = await drain(sized, { pageSize: 1, maxItems: 100, id })
    expect(out.bytes).toBe(300)
    expect(out.pages).toBe(2)
  })
})

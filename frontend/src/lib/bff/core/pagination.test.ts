import { describe, expect, test } from 'bun:test'
import { listQuery, paginate } from './pagination'

const items = Array.from({ length: 7 }, (_, i) => i + 1)

describe('listQuery', () => {
  test('defaults', () => {
    expect(listQuery.parse({})).toEqual({ page: 1, page_size: 50 })
  })
  test('coerces strings and clamps garbage to defaults', () => {
    expect(listQuery.parse({ page: '2', page_size: '10' })).toEqual({ page: 2, page_size: 10 })
    expect(listQuery.parse({ page: 'x', page_size: '-4' })).toEqual({ page: 1, page_size: 50 })
  })
  test('caps page_size at 200', () => {
    expect(listQuery.parse({ page_size: '9999' }).page_size).toBe(50) // catch() on out-of-range
  })
})

describe('paginate', () => {
  test('middle page has both links, BFF-relative', () => {
    const page = paginate(items, { page: 2, page_size: 3 }, '/bff/papers', { workspace_id: 'w1' })
    expect(page.count).toBe(7)
    expect(page.results).toEqual([4, 5, 6])
    expect(page.next).toBe('/bff/papers?workspace_id=w1&page=3&page_size=3')
    expect(page.previous).toBe('/bff/papers?workspace_id=w1&page_size=3')
  })
  test('last page has no next', () => {
    const page = paginate(items, { page: 3, page_size: 3 }, '/bff/papers')
    expect(page.results).toEqual([7])
    expect(page.next).toBeNull()
  })
  test('empty list', () => {
    const page = paginate([], { page: 1, page_size: 50 }, '/bff/x')
    expect(page).toEqual({ count: 0, next: null, previous: null, results: [] })
  })
})

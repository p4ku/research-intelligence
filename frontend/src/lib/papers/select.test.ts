import { describe, expect, test } from 'bun:test'
import { byValueAsc, byValueDesc } from './select'

describe('byValueDesc / byValueAsc', () => {
  const values = [5, null, 3, 8, null, 1]
  test('descending, nulls last', () => {
    expect([...values].sort(byValueDesc)).toEqual([8, 5, 3, 1, null, null])
  })
  test('ascending keeps nulls last (regression: flipping the args put them first)', () => {
    expect([...values].sort(byValueAsc)).toEqual([1, 3, 5, 8, null, null])
  })
})

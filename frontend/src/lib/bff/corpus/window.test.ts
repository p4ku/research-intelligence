import { describe, expect, test } from 'bun:test'
import { extractionCutoff, truncation } from './window'

describe('extractionCutoff', () => {
  test('is the oldest ingest instant, whatever the order or the fraction', () => {
    expect(
      extractionCutoff([
        { created_at: '2026-09-03T10:00:00Z' },
        { created_at: '2026-08-30T09:00:00.5Z' },
        // Later than the row above, though it sorts before it as a string.
        { created_at: '2026-08-30T09:00:01Z' },
      ]),
    ).toBe(Date.parse('2026-08-30T09:00:00.5Z'))
  })

  test('is null for no papers', () => {
    expect(extractionCutoff([])).toBeNull()
  })
})

describe('truncation', () => {
  test('only a walk that reached the cap is truncated', () => {
    expect(truncation(2000, 2500, 2000)).toEqual({ kept: 2000, total: 2500 })
    expect(truncation(2000, 2000, 2000)).toBeUndefined()
    // A row deduped mid-walk leaves the count one short without dropping anything.
    expect(truncation(1999, 2000, 2000)).toBeUndefined()
    expect(truncation(55, 55, 2000)).toBeUndefined()
  })
})

import { describe, expect, test } from 'bun:test'
import { extractionCutoff } from './window'

describe('extractionCutoff', () => {
  test('is the oldest ingest time, whatever the order', () => {
    expect(
      extractionCutoff([
        { created_at: '2026-09-03T10:00:00Z' },
        { created_at: '2026-08-30T09:00:00Z' },
        { created_at: '2026-09-01T00:00:00Z' },
      ]),
    ).toBe('2026-08-30T09:00:00Z')
  })

  test('is null for no papers', () => {
    expect(extractionCutoff([])).toBeNull()
  })
})

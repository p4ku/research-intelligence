import { describe, expect, test } from 'bun:test'
import { compareInstants } from './instant'

describe('compareInstants', () => {
  test('an instant without a fraction sorts before one in the same second', () => {
    // As strings 'Z' > '.', which put the earlier instant last.
    expect(compareInstants('2026-09-08T10:00:00Z', '2026-09-08T10:00:00.412000Z')).toBeLessThan(0)
  })

  test('microseconds decide inside the same millisecond', () => {
    expect(
      compareInstants('2026-09-08T10:00:00.412300Z', '2026-09-08T10:00:00.412700Z'),
    ).toBeLessThan(0)
    expect(compareInstants('2026-09-08T10:00:00Z', '2026-09-08T10:00:00.000400Z')).toBeLessThan(0)
    expect(compareInstants('2026-09-08T10:00:00.412Z', '2026-09-08T10:00:00.412700Z')).toBeLessThan(
      0,
    )
  })

  test('offsets are honoured', () => {
    expect(compareInstants('2026-09-08T12:00:00+02:00', '2026-09-08T10:00:00Z')).toBe(0)
    expect(compareInstants('2026-09-08T12:00:01+02:00', '2026-09-08T10:00:00Z')).toBeGreaterThan(0)
  })

  test('equal or unparseable compares as 0', () => {
    expect(compareInstants('2026-09-08T10:00:00Z', '2026-09-08T10:00:00Z')).toBe(0)
    expect(compareInstants('garbage', '2026-09-08T10:00:00Z')).toBe(0)
    expect(compareInstants('2026-09-08T10:00:00Z', 'garbage')).toBe(0)
  })
})

import { describe, expect, test } from 'bun:test'
import { editionFor } from './select'

const day = (date: string, run_id: string, clock = '12:00') => ({
  date,
  run_id,
  generated_at: `${date}T${clock}:00Z`,
})
// Newest first, as the service lists them: two runs on the 8th, one on the 7th.
const editions = [
  day('2026-09-08', 'b', '12:00'),
  day('2026-09-08', 'a', '09:00'),
  day('2026-09-07', 'z'),
]

describe('editionFor', () => {
  test('the run named in the URL, when it ran that day', () => {
    expect(editionFor(editions, '2026-09-08', 'a')?.run_id).toBe('a')
    expect(editionFor(editions, '2026-09-08', 'b')?.run_id).toBe('b')
  })

  test("without a run, the day's newest — the older same-day run stays reachable by id", () => {
    expect(editionFor(editions, '2026-09-08')?.run_id).toBe('b')
    expect(editionFor(editions, '2026-09-07')?.run_id).toBe('z')
  })

  test("a run that is not one of the day's falls back to the day's newest", () => {
    expect(editionFor(editions, '2026-09-08', 'z')?.run_id).toBe('b')
    expect(editionFor(editions, '2026-09-08', 'nope')?.run_id).toBe('b')
  })

  test('newest means latest completion, whatever order the list arrives in', () => {
    // Run a started first and finished last: a start-ordered list puts it second.
    const inverted = [day('2026-09-08', 'b', '10:00'), day('2026-09-08', 'a', '15:00')]
    expect(editionFor(inverted, '2026-09-08')?.run_id).toBe('a')
    expect(editionFor([...inverted].reverse(), '2026-09-08')?.run_id).toBe('a')
    // Without a completion stamp the day itself is the stamp, and loses to any clock.
    const stampless = [{ date: '2026-09-08', run_id: 'c', generated_at: null }, ...inverted]
    expect(editionFor(stampless, '2026-09-08')?.run_id).toBe('a')
  })

  test('a day with no edition is null, whatever the run', () => {
    expect(editionFor(editions, '2026-09-06')).toBeNull()
    expect(editionFor(editions, '2026-09-06', 'a')).toBeNull()
  })
})

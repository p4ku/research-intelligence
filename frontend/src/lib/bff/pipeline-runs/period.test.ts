import { describe, expect, test } from 'bun:test'
import { isRetryable, runPeriod } from './period'

describe('runPeriod', () => {
  test('explicit dates, trimmed to the day', () => {
    expect(
      runPeriod({ start_date: '2026-08-01T00:00:00', end_date: '2026-09-05', n_last_days: 7 }),
    ).toEqual({ period_start: '2026-08-01', period_end: '2026-09-05', lookback_days: null })
  })

  test('one-sided windows keep the side they have', () => {
    expect(runPeriod({ start_date: '2026-08-01', end_date: null })).toEqual({
      period_start: '2026-08-01',
      period_end: null,
      lookback_days: null,
    })
    expect(runPeriod({ end_date: '2026-08-31' })).toEqual({
      period_start: null,
      period_end: '2026-08-31',
      lookback_days: null,
    })
  })

  test('a relative window only when there are no dates', () => {
    expect(runPeriod({ n_last_days: 7 })).toEqual({
      period_start: null,
      period_end: null,
      lookback_days: 7,
    })
    expect(runPeriod({ n_last_days: 0 }).lookback_days).toBeNull()
    expect(runPeriod({ n_last_days: 2.5 }).lookback_days).toBeNull()
  })

  test('a run with MCP-only options is not retryable from Home', () => {
    expect(isRetryable({ start_date: '2026-08-01', end_date: '2026-08-31' })).toBe(true)
    expect(isRetryable(null)).toBe(true)
    expect(isRetryable({ limit: 20 })).toBe(false)
    expect(isRetryable({ query_prefix: 'quantum' })).toBe(false)
    expect(isRetryable({ limit: null, query_prefix: '' })).toBe(true)
  })

  test('missing or malformed configuration reads as no period', () => {
    const none = { period_start: null, period_end: null, lookback_days: null }
    expect(runPeriod(null)).toEqual(none)
    expect(runPeriod(undefined)).toEqual(none)
    expect(runPeriod({})).toEqual(none)
    expect(runPeriod({ start_date: 'last week', end_date: '' })).toEqual(none)
  })
})

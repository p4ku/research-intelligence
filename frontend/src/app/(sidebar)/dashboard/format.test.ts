import type { T } from '@/lib/i18n'
import { describe, expect, test } from 'bun:test'
import {
  formatAuthors,
  formatClock,
  formatDay,
  formatPeriod,
  periodLabel,
  shiftDays,
} from './format'

const t: T = (s) => s

describe('formatDay', () => {
  test('English writes the spec’s "Sep", German keeps its dots', () => {
    expect(formatDay('2026-09-05', 'en')).toBe('5 Sep 2026')
    expect(formatDay('2026-09-05', 'de')).toBe('5. Sept. 2026')
  })

  test('an instant renders as its UTC day, whatever the zone', () => {
    expect(formatDay('2026-08-31T23:30:00.000Z', 'en')).toBe('31 Aug 2026')
  })
})

describe('formatPeriod', () => {
  test('within one month', () => {
    expect(formatPeriod('2026-08-01', '2026-08-31', 'en')).toBe('1–31 Aug 2026')
    expect(formatPeriod('2026-08-01', '2026-08-31', 'de')).toBe('1.–31. Aug. 2026')
  })

  test('within one year', () => {
    expect(formatPeriod('2026-08-01', '2026-09-05', 'en')).toBe('1 Aug–5 Sep 2026')
    expect(formatPeriod('2026-08-01', '2026-09-05', 'de')).toBe('1. Aug.–5. Sept. 2026')
  })

  test('across years', () => {
    expect(formatPeriod('2025-12-01', '2026-01-05', 'en')).toBe('1 Dec 2025–5 Jan 2026')
  })
})

describe('formatClock', () => {
  test('UTC, 24-hour', () => {
    expect(formatClock('2026-09-03T07:12:00Z')).toBe('07:12')
    expect(formatClock('2026-09-03T23:05:00+02:00')).toBe('21:05')
  })
})

describe('periodLabel', () => {
  const base = { period_start: null, period_end: null, lookback_days: null, run_date: '2026-08-31' }

  test('explicit dates read as a range', () => {
    expect(
      periodLabel({ ...base, period_start: '2026-08-01', period_end: '2026-09-05' }, t, 'en'),
    ).toBe('1 Aug–5 Sep 2026')
  })

  test('one-sided windows say which side', () => {
    expect(periodLabel({ ...base, period_start: '2026-08-01' }, t, 'en')).toBe('From 1 Aug 2026')
    expect(periodLabel({ ...base, period_end: '2026-08-31' }, t, 'en')).toBe('Until 31 Aug 2026')
  })

  test('a relative window, then the trigger day as the last resort', () => {
    expect(periodLabel({ ...base, lookback_days: 7 }, t, 'en')).toBe('Last 7 days')
    expect(periodLabel(base, t, 'en')).toBe('31 Aug 2026')
  })
})

describe('shiftDays', () => {
  test('goes back across a month boundary', () => {
    expect(shiftDays('2026-09-07', -30)).toBe('2026-08-08')
    expect(shiftDays('2026-03-01', -1)).toBe('2026-02-28')
  })
})

describe('formatAuthors', () => {
  test('three names, then et al.', () => {
    expect(formatAuthors(['A. Okafor', 'B. Lindqvist'])).toBe('A. Okafor, B. Lindqvist')
    expect(formatAuthors(['A', 'B', 'C', 'D'])).toBe('A, B, C et al.')
    expect(formatAuthors([])).toBe('')
  })
})

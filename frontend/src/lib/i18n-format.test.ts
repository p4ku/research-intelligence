/**
 * The locale-aware formatters every screen routes its numbers and dates
 * through. German is not English with a different decimal mark: it groups on
 * dots, separates the percent sign with a narrow no-break space (DIN 5008),
 * and writes an ordinal dot after the day. These are the readings the rest of
 * the app is tested against, so they are pinned here rather than left to
 * whatever ICU data the runtime ships.
 *
 * The dictionary itself is guarded by i18n.test.ts; this file is only about
 * the number and date shapes.
 */
import { describe, expect, test } from 'bun:test'
import { formatDate, formatNumber, formatPercent } from './i18n'

// U+202F, escaped so a plain space cannot creep in unnoticed.
const NNBSP = '\u202f'

describe('formatNumber', () => {
  test('groups thousands the way each locale does', () => {
    expect(formatNumber(1234.5, 'en')).toBe('1,234.5')
    expect(formatNumber(1234.5, 'de')).toBe('1.234,5')
  })

  test('`digits` fixes the fraction digits, decimal comma included', () => {
    expect(formatNumber(88.5, 'de', 1)).toBe('88,5')
    expect(formatNumber(88.5, 'en', 1)).toBe('88.5')
  })

  test('`maxDigits` alone widens the ceiling without forcing a floor', () => {
    // "at most two decimals" — an integer must stay an integer, not "7.00".
    expect(formatNumber(7, 'en', undefined, 2)).toBe('7')
    expect(formatNumber(7, 'de', undefined, 2)).toBe('7')
    expect(formatNumber(88.456, 'en', undefined, 2)).toBe('88.46')
  })
})

describe('formatPercent', () => {
  test('German separates the sign with a narrow no-break space, English does not', () => {
    expect(formatPercent(41, 'de')).toBe(`41${NNBSP}%`)
    expect(formatPercent(41, 'en')).toBe('41%')
  })
})

describe('formatDate', () => {
  test('a day and a late-UTC instant on that day render as the same day', () => {
    // The whole point of the explicit UTC zone: a German reader at UTC+2 must
    // not see a 23:30Z paper dated the following day.
    expect(formatDate('2026-09-01', 'de')).toBe('1. Sept. 2026')
    expect(formatDate('2026-09-01T23:30:00Z', 'de')).toBe('1. Sept. 2026')
  })

  test('English keeps its month-first short form', () => {
    expect(formatDate('2026-09-01T23:30:00Z', 'en')).toContain('Sep 1')
  })
})

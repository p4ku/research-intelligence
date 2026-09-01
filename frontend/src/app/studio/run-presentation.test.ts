import { describe, expect, test } from 'bun:test'
import { formatDuration, formatTokens, formatUsd } from './run-presentation'

describe('formatDuration', () => {
  test('sub-second, seconds, minutes and hours', () => {
    expect(formatDuration(0.08)).toBe('0.08s')
    expect(formatDuration(0.84)).toBe('0.84s')
    expect(formatDuration(43.0)).toBe('43.0s')
    expect(formatDuration(68)).toBe('1m 08s')
    expect(formatDuration(233)).toBe('3m 53s')
    expect(formatDuration(3600)).toBe('1h 00m')
    // The zombie watchdog's 120-minute pipeline ceiling must not read "120m".
    expect(formatDuration(7200)).toBe('2h 00m')
    expect(formatDuration(7261)).toBe('2h 01m')
  })

  test('never emits a 60-second remainder', () => {
    // `duration_seconds` is a 6-decimal float, so remainders land arbitrarily
    // close to a minute boundary. Rounding the remainder on its own yields
    // "1m 60s"; rounding to whole seconds before splitting cannot.
    expect(formatDuration(119.5)).toBe('2m 00s')
    expect(formatDuration(119.7)).toBe('2m 00s')
    expect(formatDuration(3599.7)).toBe('1h 00m')
    for (let s = 59; s < 7200; s += 0.1) {
      expect(formatDuration(s)).not.toContain(' 60s')
    }
  })

  test('the seconds/minutes boundary does not print 60.0s', () => {
    expect(formatDuration(59.9)).toBe('59.9s')
    expect(formatDuration(59.96)).toBe('1m 00s')
  })

  test('null, non-finite and negative all render as an em dash', () => {
    expect(formatDuration(null)).toBe('—')
    expect(formatDuration(Number.NaN)).toBe('—')
    expect(formatDuration(Number.POSITIVE_INFINITY)).toBe('—')
    expect(formatDuration(-5)).toBe('—')
  })
})

describe('formatUsd', () => {
  test('precision follows magnitude', () => {
    expect(formatUsd(0.0029)).toBe('$0.0029')
    expect(formatUsd(0.05)).toBe('$0.05')
    expect(formatUsd(1.2269)).toBe('$1.23')
  })

  test('unmeasured is an em dash, measured zero is $0', () => {
    // Five of the seven step types record no cost at all. That must not read
    // as a measurement of zero.
    expect(formatUsd(null)).toBe('—')
    expect(formatUsd(0)).toBe('$0')
  })

  test('negatives keep the sign outside the currency symbol', () => {
    // The unattributed-spend figure is signed: steps can book more than the
    // run total. "$-0.0500" is not a currency amount.
    expect(formatUsd(-0.05)).toBe('-$0.05')
    expect(formatUsd(-0.0004)).toBe('-$0.0004')
    expect(formatUsd(-1.5)).toBe('-$1.50')
  })
})

describe('formatTokens', () => {
  test('groups digits, and null is an em dash', () => {
    expect(formatTokens(1492568)).toBe('1,492,568')
    expect(formatTokens(0)).toBe('0')
    expect(formatTokens(null)).toBe('—')
  })
})

import { describe, expect, test } from 'bun:test'
import { describeCron } from './cron'

describe('describeCron', () => {
  test('weekly, both languages', () => {
    expect(describeCron('0 9 * * 5', 'en')).toBe('Fridays at 09:00')
    expect(describeCron('0 9 * * 5', 'de')).toBe('freitags um 09:00 Uhr')
    expect(describeCron('30 7 * * 1', 'de')).toBe('montags um 07:30 Uhr')
  })
  test('sunday accepts 0 and 7', () => {
    expect(describeCron('0 8 * * 0', 'en')).toBe('Sundays at 08:00')
    expect(describeCron('0 8 * * 7', 'en')).toBe('Sundays at 08:00')
  })
  test('daily', () => {
    expect(describeCron('15 6 * * *', 'en')).toBe('daily at 06:15')
    expect(describeCron('15 6 * * *', 'de')).toBe('täglich um 06:15 Uhr')
  })
  test('anything fancier stays raw', () => {
    expect(describeCron('0 9 * * 1-5', 'en')).toBeNull()
    expect(describeCron('*/5 * * * *', 'en')).toBeNull()
    expect(describeCron('0 9 1 * *', 'en')).toBeNull()
    expect(describeCron('not a cron', 'en')).toBeNull()
    expect(describeCron('99 9 * * *', 'en')).toBeNull()
  })
})

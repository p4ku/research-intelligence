import { describe, expect, test } from 'bun:test'
import { cadence, nextWordEnd } from './use-smooth-text'

describe('nextWordEnd', () => {
  test('advances one word at a time, whitespace included', () => {
    const text = 'Read as a capability'
    expect(nextWordEnd(text, 0)).toBe(5) // "Read "
    expect(nextWordEnd(text, 5)).toBe(8) // "as "
    expect(nextWordEnd(text, 8)).toBe(10) // "a "
  })

  test('waits on a word that is still being written', () => {
    expect(nextWordEnd('Read as a capab', 10)).toBeNull()
  })

  test('keeps leading whitespace and newlines with the word that follows', () => {
    const text = 'cite.\n\nWhat it '
    expect(nextWordEnd(text, 5)).toBe(12) // "\n\nWhat "
  })

  test('is null at the end', () => {
    expect(nextWordEnd('done ', 5)).toBeNull()
  })
})

describe('cadence', () => {
  test('quickens as the backlog grows', () => {
    expect(cadence(10, false)).toBeGreaterThan(cadence(100, false))
    expect(cadence(100, false)).toBeGreaterThan(cadence(300, false))
    expect(cadence(300, false)).toBeGreaterThan(cadence(1000, false))
  })

  test('finishes briskly once the stream has ended, still word by word', () => {
    expect(cadence(10, true)).toBeLessThan(cadence(10, false))
    expect(cadence(10, true)).toBeGreaterThan(0)
  })
})

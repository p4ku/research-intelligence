import { describe, expect, test } from 'bun:test'
import { intEnv } from './env'

describe('intEnv', () => {
  test('absent or blank → the fallback', () => {
    expect(intEnv('X', 7, { env: {} })).toBe(7)
    expect(intEnv('X', 7, { env: { X: '  ' } })).toBe(7)
  })

  test('an integer at or above the floor is read', () => {
    expect(intEnv('X', 7, { min: 1, env: { X: '42' } })).toBe(42)
    expect(intEnv('X', 7, { min: 1, env: { X: ' 1 ' } })).toBe(1)
  })

  test('garbage, fractions and values under the floor fall back', () => {
    expect(intEnv('X', 7, { min: 1, env: { X: 'lots' } })).toBe(7)
    expect(intEnv('X', 7, { min: 1, env: { X: '2.5' } })).toBe(7)
    expect(intEnv('X', 7, { min: 1, env: { X: '0' } })).toBe(7)
  })
})

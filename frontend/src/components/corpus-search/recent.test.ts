import { describe, expect, test } from 'bun:test'
import { clearRecent, pushRecent, readRecent, RECENT_KEY, type RecentStore } from './recent'

function memoryStore(initial: Record<string, string> = {}): RecentStore {
  const data = new Map(Object.entries(initial))
  return {
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, v),
    removeItem: (k) => void data.delete(k),
  }
}

describe('recent searches', () => {
  test('newest first, deduped case-insensitively, capped at five', () => {
    const store = memoryStore()
    for (const q of ['a', 'b', 'c', 'd', 'e', 'f']) pushRecent(q, store)
    expect(readRecent(store)).toEqual(['f', 'e', 'd', 'c', 'b'])
    expect(pushRecent('  D ', store)).toEqual(['D', 'f', 'e', 'c', 'b'])
    expect(pushRecent('   ', store)).toEqual(['D', 'f', 'e', 'c', 'b'])
  })

  test('malformed, missing, or throwing storage reads as nothing', () => {
    expect(readRecent(memoryStore({ [RECENT_KEY]: '{oops' }))).toEqual([])
    expect(readRecent(memoryStore({ [RECENT_KEY]: '[1, "x"]' }))).toEqual(['x'])
    expect(readRecent(undefined)).toEqual([])
    const broken: RecentStore = {
      getItem: () => {
        throw new Error('blocked')
      },
      setItem: () => {
        throw new Error('blocked')
      },
      removeItem: () => {
        throw new Error('blocked')
      },
    }
    expect(readRecent(broken)).toEqual([])
    expect(pushRecent('x', broken)).toEqual(['x'])
    expect(() => clearRecent(broken)).not.toThrow()
  })

  test('clear empties the list', () => {
    const store = memoryStore()
    pushRecent('x', store)
    clearRecent(store)
    expect(readRecent(store)).toEqual([])
  })
})

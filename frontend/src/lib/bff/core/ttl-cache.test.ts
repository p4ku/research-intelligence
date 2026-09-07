import { describe, expect, test } from 'bun:test'
import { TtlCache } from './ttl-cache'

function clock(start = 1_000) {
  let t = start
  return { now: () => t, tick: (ms: number) => (t += ms) }
}

describe('TtlCache', () => {
  test('a fresh key shares one load', async () => {
    const c = clock()
    const cache = new TtlCache<number>({ ttlMs: 100, maxEntries: 4, now: c.now })
    let loads = 0
    const load = async () => ++loads
    const a = cache.get('k', load)
    const b = cache.get('k', load)
    expect(a).toBe(b)
    expect(await a).toBe(1)
    expect(loads).toBe(1)
  })

  test('reloads after the ttl', async () => {
    const c = clock()
    const cache = new TtlCache<number>({ ttlMs: 100, maxEntries: 4, now: c.now })
    let loads = 0
    const load = async () => ++loads
    await cache.get('k', load)
    c.tick(99)
    await cache.get('k', load)
    expect(loads).toBe(1)
    c.tick(2)
    await cache.get('k', load)
    expect(loads).toBe(2)
  })

  test('a rejected load is not kept', async () => {
    const cache = new TtlCache<number>({ ttlMs: 100, maxEntries: 4 })
    let loads = 0
    const load = async () => {
      loads += 1
      if (loads === 1) throw new Error('boom')
      return loads
    }
    await expect(cache.get('k', load)).rejects.toThrow('boom')
    expect(cache.size).toBe(0)
    expect(await cache.get('k', load)).toBe(2)
  })

  test('peek never loads and respects the ttl; delete drops one key', async () => {
    const c = clock()
    const cache = new TtlCache<string>({ ttlMs: 100, maxEntries: 4, now: c.now })
    expect(cache.peek('k')).toBeUndefined()
    const load = cache.get('k', async () => 'v')
    expect(cache.peek('k')).toBe(load)
    await cache.get('other', async () => 'o')
    cache.delete('k')
    expect(cache.peek('k')).toBeUndefined()
    expect(await cache.peek('other')).toBe('o')
    c.tick(101)
    expect(cache.peek('other')).toBeUndefined()
    expect(cache.size).toBe(0)
  })

  test('evicts the oldest key past maxEntries and clears', async () => {
    const cache = new TtlCache<string>({ ttlMs: 100, maxEntries: 2 })
    await cache.get('a', async () => 'a')
    await cache.get('b', async () => 'b')
    await cache.get('c', async () => 'c')
    expect(cache.size).toBe(2)
    let reloaded = false
    await cache.get('a', async () => {
      reloaded = true
      return 'a2'
    })
    expect(reloaded).toBe(true)
    cache.clear()
    expect(cache.size).toBe(0)
  })
})

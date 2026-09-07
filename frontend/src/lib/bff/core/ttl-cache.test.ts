import { describe, expect, test } from 'bun:test'
import { clock } from './test-clock'
import { TtlCache } from './ttl-cache'

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

  test('evicts the least recently used key past maxEntries and clears', async () => {
    const cache = new TtlCache<string>({ ttlMs: 100, maxEntries: 2 })
    await cache.get('a', async () => 'a')
    await cache.get('b', async () => 'b')
    // A hit on the older key keeps it; the untouched one goes.
    expect(await cache.peek('a')).toBe('a')
    await cache.get('c', async () => 'c')
    expect(cache.size).toBe(2)
    expect(await cache.peek('a')).toBe('a')
    expect(cache.peek('b')).toBeUndefined()
    cache.clear()
    expect(cache.size).toBe(0)
  })

  describe('a byte budget', () => {
    const sized = () =>
      new TtlCache<number>({ ttlMs: 100, maxEntries: 10, maxBytes: 100, sizeOf: (n) => n })

    test('weighs an entry once it settles and evicts least recently used past the budget', async () => {
      const cache = sized()
      await cache.get('a', async () => 40)
      await cache.get('b', async () => 40)
      expect(cache.bytes).toBe(80)
      // A hit keeps `a` alive; the budget takes `b`.
      expect(await cache.peek('a')).toBe(40)
      await cache.get('c', async () => 40)
      expect(cache.peek('b')).toBeUndefined()
      expect(await cache.peek('a')).toBe(40)
      expect(cache.bytes).toBe(80)
      expect(cache.size).toBe(2)
    })

    test('delete, clear and expiry release bytes', async () => {
      const c = clock()
      const cache = new TtlCache<number>({
        ttlMs: 100,
        maxEntries: 10,
        maxBytes: 100,
        sizeOf: (n) => n,
        now: c.now,
      })
      await cache.get('a', async () => 30)
      await cache.get('b', async () => 30)
      cache.delete('a')
      expect(cache.bytes).toBe(30)
      c.tick(101)
      expect(cache.peek('b')).toBeUndefined()
      expect(cache.bytes).toBe(0)
      await cache.get('c', async () => 30)
      cache.clear()
      expect(cache.bytes).toBe(0)
    })

    test('an entry invalidated while loading adds nothing when it settles', async () => {
      const cache = sized()
      let release!: (n: number) => void
      const pending = cache.get('a', () => new Promise<number>((r) => (release = r)))
      cache.delete('a')
      release(60)
      await pending
      expect(cache.bytes).toBe(0)
      expect(cache.size).toBe(0)
    })

    test('a single entry over the whole budget is kept until the next insert', async () => {
      const cache = sized()
      await cache.get('big', async () => 500)
      expect(cache.size).toBe(1)
      expect(await cache.peek('big')).toBe(500)
      await cache.get('small', async () => 10)
      expect(cache.peek('big')).toBeUndefined()
      expect(cache.bytes).toBe(10)
    })

    test('an in-flight entry weighs nothing and is never evicted for bytes', async () => {
      const cache = sized()
      await cache.get('a', async () => 90)
      let release!: (n: number) => void
      const pending = cache.get('b', () => new Promise<number>((r) => (release = r)))
      expect(cache.size).toBe(2)
      release(90)
      await pending
      // `b` settled over budget: the least recently used settled key (`a`) goes.
      expect(cache.peek('a')).toBeUndefined()
      expect(await cache.peek('b')).toBe(90)
    })
  })
})

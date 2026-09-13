import { describe, expect, test } from 'bun:test'
import { problem } from '../core/problem'
import { clock } from '../core/test-clock'
import { createSnapshotStore, effectiveTrust } from './store'

/** A store over counters, so every test can say exactly what was called. */
function harness({
  version = 'v1',
  probeError = null as unknown,
  loadError = null as unknown,
} = {}) {
  const c = clock()
  const calls = { probe: 0, load: 0 }
  const state = { version, probeError, loadError }
  const store = createSnapshotStore<{ n: number }>({
    probe: async () => {
      calls.probe += 1
      if (state.probeError) throw state.probeError
      return state.version
    },
    load: async () => {
      calls.load += 1
      if (state.loadError) throw state.loadError
      return { n: calls.load }
    },
    ttlMs: 600_000,
    maxEntries: 4,
    now: c.now,
  })
  return { store, calls, state, clock: c }
}

describe('createSnapshotStore', () => {
  test('no key: loads uncached every time, never probes', async () => {
    const { store, calls } = harness()
    await store.get(null)
    await store.get(null)
    expect(calls).toEqual({ probe: 0, load: 2 })
  })

  test('a miss probes and loads together, and concurrent misses share it', async () => {
    const { store, calls } = harness()
    const [a, b] = await Promise.all([store.get('k'), store.get('k')])
    expect(a).toBe(b)
    expect(calls).toEqual({ probe: 1, load: 1 })
  })

  test('every read confirms the version; an unchanged one is served', async () => {
    const { store, calls, clock } = harness()
    const first = await store.get('k')
    clock.tick(1)
    expect(await store.get('k')).toBe(first)
    clock.tick(1)
    expect(await store.get('k')).toBe(first)
    expect(calls).toEqual({ probe: 3, load: 1 })
  })

  test('a read that trusts a recent confirmation skips the probe', async () => {
    const { store, calls, clock } = harness()
    const first = await store.get('k')
    clock.tick(9_999)
    expect(await store.get('k', { trustMs: 10_000 })).toBe(first)
    expect(calls.probe).toBe(1)
    clock.tick(2)
    await store.get('k', { trustMs: 10_000 })
    expect(calls.probe).toBe(2)
  })

  test('a changed version reloads exactly once', async () => {
    const { store, calls, state, clock } = harness()
    const first = await store.get('k')
    state.version = 'v2'
    clock.tick(1)
    const [a, b] = await Promise.all([store.get('k'), store.get('k')])
    expect(a).not.toBe(first)
    expect(a).toBe(b)
    expect(calls).toEqual({ probe: 2, load: 2 })
  })

  test('a 401 from the probe is rethrown, warm or cold', async () => {
    const { store, state, clock } = harness()
    await store.get('k')
    state.probeError = problem('unauthenticated')
    clock.tick(1)
    await expect(store.get('k')).rejects.toMatchObject({ problem: { status: 401 } })
    const cold = harness({ probeError: problem('unauthenticated') })
    await expect(cold.store.get('k')).rejects.toMatchObject({ problem: { status: 401 } })
  })

  test('any other probe failure serves the entry unconfirmed, so a trusting read still probes', async () => {
    const { store, calls, state, clock } = harness()
    const first = await store.get('k')
    state.probeError = problem('upstream-unavailable')
    clock.tick(20_000)
    expect(await store.get('k')).toBe(first)
    expect(await store.get('k', { trustMs: 10_000 })).toBe(first)
    expect(calls).toEqual({ probe: 3, load: 1 })
    state.probeError = null
    expect(await store.get('k')).toBe(first)
    clock.tick(1)
    await store.get('k', { trustMs: 10_000 })
    expect(calls.probe).toBe(4)
  })

  test('a probe failure on a miss still loads, and keeps nothing', async () => {
    const { store, calls, state, clock } = harness({ probeError: problem('upstream-unavailable') })
    await store.get('k')
    expect(calls).toEqual({ probe: 1, load: 1 })
    state.probeError = null
    clock.tick(1)
    await store.get('k')
    expect(calls).toEqual({ probe: 2, load: 2 })
  })

  test('a cold load whose data settled before the version is served once, never kept', async () => {
    const c = clock()
    const calls = { probe: 0, load: 0 }
    let releaseProbe = () => {}
    const store = createSnapshotStore<number>({
      probe: () =>
        new Promise<string>((resolve) => {
          calls.probe += 1
          releaseProbe = () => resolve('v-new')
        }),
      load: async () => ++calls.load,
      ttlMs: 600_000,
      maxEntries: 4,
      now: c.now,
    })
    const pending = store.get('k')
    // The data has landed; only now does the (possibly newer) version arrive.
    await Promise.resolve()
    await Promise.resolve()
    releaseProbe()
    expect(await pending).toBe(1)
    // Nothing trusted was kept, so the next read loads again under a settled version.
    const next = store.get('k')
    releaseProbe()
    expect(await next).toBe(2)
  })

  test('a failed load is not kept', async () => {
    const { store, calls, state } = harness({ loadError: new Error('boom') })
    await expect(store.get('k')).rejects.toThrow('boom')
    state.loadError = null
    await store.get('k')
    expect(calls.load).toBe(2)
  })

  test('invalidate forces a reload, for one key or all', async () => {
    const { store, calls } = harness()
    await store.get('a')
    await store.get('b')
    store.invalidate('a')
    await store.get('a')
    await store.get('b')
    expect(calls.load).toBe(3)
    store.invalidate()
    await store.get('a')
    await store.get('b')
    expect(calls.load).toBe(5)
  })

  test('the ttl is a ceiling even for a confirmed version', async () => {
    const { store, calls, clock } = harness()
    await store.get('k')
    clock.tick(600_001)
    await store.get('k')
    expect(calls.load).toBe(2)
  })

  test('a read that trusts nothing does not inherit an in-flight probe that predates it', async () => {
    const c = clock()
    const calls = { probe: 0, load: 0 }
    const probes: Array<(v: string) => void> = []
    const loads: Array<() => void> = []
    const store = createSnapshotStore<number>({
      probe: () =>
        new Promise<string>((resolve) => {
          calls.probe += 1
          probes.push(resolve)
        }),
      load: () =>
        new Promise<number>((resolve) => {
          const n = ++calls.load
          loads.push(() => resolve(n))
        }),
      ttlMs: 600_000,
      maxEntries: 4,
      now: c.now,
    })
    const settle = async () => {
      for (let i = 0; i < 4; i += 1) await Promise.resolve()
    }
    const first = store.get('k')
    await settle()
    probes.shift()!('v1') // the version lands before the data, so the entry is kept
    await settle()
    loads.shift()!()
    expect(await first).toBe(1)
    c.tick(10)
    // A trusting read starts a revalidation; its probe is still out when the
    // run completes and, a moment later, a ledger-reading request (trust 0) arrives.
    const trusting = store.get('k', { trustMs: 5 })
    await settle()
    c.tick(1)
    const exact = store.get('k', { trustMs: 0 })
    await settle()
    expect(calls.probe).toBe(2)
    probes.shift()!('v1') // the old probe: saw the ledger before completion
    expect(await trusting).toBe(1)
    await settle()
    // The exact read probed on its own after the stale one settled, and reloads.
    expect(calls.probe).toBe(3)
    probes.shift()!('v2')
    await settle()
    loads.shift()!()
    expect(await exact).toBe(2)
  })

  test('a byte budget evicts the least recently used user before the key count does', async () => {
    const calls = { load: 0 }
    const store = createSnapshotStore<{ bytes: number }>({
      probe: async () => 'v1',
      load: async () => {
        calls.load += 1
        return { bytes: 60 }
      },
      ttlMs: 600_000,
      maxEntries: 8,
      maxBytes: 100,
      sizeOf: (s) => s.bytes,
    })
    await store.get('a')
    await store.get('b')
    // `b` evicted `a` (120 > 100); reading `a` again is a cold load.
    await store.get('a')
    expect(calls.load).toBe(3)
    await store.get('a')
    expect(calls.load).toBe(3)
  })
})

describe('createSnapshotStore shared', () => {
  test('two stores under one name hold one set of entries, each with its own probe and load', async () => {
    const c = clock()
    const calls = { a: 0, b: 0, solo: 0 }
    const make = (name: keyof typeof calls, shared?: string) =>
      createSnapshotStore<{ n: number }>({
        probe: async () => 'v1',
        load: async () => {
          calls[name] += 1
          return { n: calls[name] }
        },
        ttlMs: 600_000,
        maxEntries: 4,
        now: c.now,
        shared,
      })
    // Module-layer twins of one store: the second must see what the first loaded.
    const twins = `test-${Math.random()}`
    const a = make('a', twins)
    const b = make('b', twins)
    const first = await a.get('k')
    c.tick(1)
    expect(await b.get('k')).toBe(first)
    expect(calls).toEqual({ a: 1, b: 0, solo: 0 })
    // An invalidation through either twin reaches both.
    b.invalidate()
    c.tick(1)
    await a.get('k')
    expect(calls).toEqual({ a: 2, b: 0, solo: 0 })
    // A store with no name keeps its own entries.
    await make('solo').get('k')
    expect(calls).toEqual({ a: 2, b: 0, solo: 1 })
  })
})

describe('effectiveTrust', () => {
  test('a request that read the ledger always probes', () => {
    expect(effectiveTrust({ requested: 10_000, cooldownMs: 5_000, ledgerRequested: true })).toBe(0)
  })

  test('otherwise the cooldown applies and a request may only raise it', () => {
    expect(effectiveTrust({ requested: 0, cooldownMs: 5_000, ledgerRequested: false })).toBe(5_000)
    expect(effectiveTrust({ requested: 10_000, cooldownMs: 5_000, ledgerRequested: false })).toBe(
      10_000,
    )
    expect(effectiveTrust({ requested: 1_000, cooldownMs: 5_000, ledgerRequested: false })).toBe(
      5_000,
    )
  })
})

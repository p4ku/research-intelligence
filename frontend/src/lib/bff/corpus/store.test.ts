import { describe, expect, test } from 'bun:test'
import { problem } from '../core/problem'
import { clock } from '../core/test-clock'
import { createSnapshotStore } from './store'

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

  test('a cold load whose data settled before the version is kept unconfirmed, then settles', async () => {
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
    // The version could not be trusted, so the next read reloads under one it
    // can. It reaches the probe through the entry, so let it get there first.
    const flush = () => new Promise((resolve) => setTimeout(resolve, 0))
    const next = store.get('k')
    await flush()
    releaseProbe()
    expect(await next).toBe(2)
    // And it converges: once a load carries a settled version the store stops
    // reloading. Discarding the unconfirmed entry instead would reload here
    // too, and on every read after — a store whose load outruns its probe
    // would never cache at all, and never recover.
    c.tick(1)
    const third = store.get('k')
    await flush()
    releaseProbe()
    expect(await third).toBe(2)
    expect(calls.load).toBe(2)
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
})

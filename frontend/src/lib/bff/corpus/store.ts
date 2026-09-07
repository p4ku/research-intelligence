/**
 * The snapshot policy, with its seams injected so it can be tested without a
 * session or a backend (the house convention — see core/ttl-cache.test.ts).
 *
 * A snapshot is a value plus the version it was loaded under and when that
 * version was last confirmed. Reads go:
 *
 * - no key (no session)         → load, uncached; Django answers 401 as ever.
 * - no entry                    → probe and load together, one round trip.
 * - confirmed within the trust  → the entry, no calls at all.
 * - probe agrees                → the entry, confirmation renewed.
 * - probe disagrees             → drop, reload, store.
 * - probe fails with 401        → rethrow: the session is gone, say so.
 * - probe fails otherwise       → the entry, unconfirmed, so the next read
 *                                 probes again; with no entry, load uncached.
 *
 * The cold load stamps the probe's version only when the probe settled
 * first: data that arrived after the version can only be newer than it,
 * which the next probe catches. Data that arrived before the version could
 * be older, so it is served once and never kept. An outage therefore never
 * reads as "no data": a miss surfaces exactly the problem it surfaces
 * today. Pure apart from the injected functions.
 */
import { isUnauthenticated } from '../core/problem'
import { TtlCache } from '../core/ttl-cache'

export interface SnapshotStoreOptions<T> {
  /** The current version of the data; cheap. */
  probe: () => Promise<string>
  /** The data itself; expensive. */
  load: () => Promise<T>
  /** How long an entry may live regardless — the backstop for changes no probe explains. */
  ttlMs: number
  maxEntries: number
  /** Retained-size budget across users; needs `sizeOf`. */
  maxBytes?: number
  sizeOf?: (value: T) => number
  now?: () => number
}

/**
 * How long a read may trust a confirmed version, given what the request has
 * already done. A request that read the run ledger itself always probes —
 * the probe is that ledger, already in hand, and the render that first
 * shows a run completed must be the first with its papers. Otherwise the
 * process-wide cooldown applies, and a request may only raise it. Pure.
 */
export function effectiveTrust({
  requested,
  cooldownMs,
  ledgerRequested,
}: {
  requested: number
  cooldownMs: number
  ledgerRequested: boolean
}): number {
  if (ledgerRequested) return 0
  return Math.max(requested, cooldownMs)
}

export interface ReadOptions {
  /**
   * Skip the probe when the version was confirmed this recently. Zero (the
   * default) confirms on every read; a typing burst may trust a few seconds.
   */
  trustMs?: number
}

export interface SnapshotStore<T> {
  get(key: string | null, options?: ReadOptions): Promise<T>
  /** Forget one key, or everything. */
  invalidate(key?: string): void
}

interface Entry<T> {
  /** null when the version could not be trusted: served once, never kept. */
  version: string | null
  checkedAt: number
  value: T
}

export function createSnapshotStore<T>({
  probe,
  load,
  ttlMs,
  maxEntries,
  maxBytes,
  sizeOf,
  now = Date.now,
}: SnapshotStoreOptions<T>): SnapshotStore<T> {
  const cache = new TtlCache<Entry<T>>({
    ttlMs,
    maxEntries,
    maxBytes,
    sizeOf: sizeOf ? (entry) => sizeOf(entry.value) : undefined,
    now,
  })
  // One revalidation per key at a time, however many requests arrive together.
  const revalidating = new Map<string, Promise<Entry<T>>>()

  async function cold(): Promise<Entry<T>> {
    let loaded = false
    const [version, value] = await Promise.all([
      probe()
        .then((v) => (loaded ? null : v))
        .catch((error: unknown) => {
          if (isUnauthenticated(error)) throw error
          return null
        }),
      load().finally(() => {
        loaded = true
      }),
    ])
    return { version, checkedAt: now(), value }
  }

  async function revalidate(key: string, entry: Entry<T>): Promise<Entry<T>> {
    let version: string
    try {
      version = await probe()
    } catch (error) {
      if (isUnauthenticated(error)) throw error
      return entry
    }
    if (version === entry.version) {
      entry.checkedAt = now()
      return entry
    }
    cache.delete(key)
    return cache.get(key, async () => ({ version, checkedAt: now(), value: await load() }))
  }

  return {
    async get(key, { trustMs = 0 } = {}) {
      if (key === null) return load()
      const hit = cache.peek(key)
      if (!hit) {
        const entry = await cache.get(key, cold)
        if (entry.version === null) cache.delete(key)
        return entry.value
      }
      const entry = await hit
      // Confirmed this very moment (a concurrent request's cold load) counts as trusted.
      if (entry.version !== null && now() - entry.checkedAt <= trustMs) return entry.value
      let pending = revalidating.get(key)
      if (!pending) {
        pending = revalidate(key, entry).finally(() => revalidating.delete(key))
        revalidating.set(key, pending)
      }
      return (await pending).value
    },
    invalidate(key) {
      if (key === undefined) cache.clear()
      else cache.delete(key)
    },
  }
}

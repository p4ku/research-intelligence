/**
 * The snapshot policy, with its seams injected so it can be tested without a
 * session or a backend (the house convention — see core/ttl-cache.test.ts).
 *
 * A snapshot is a value plus the version it was loaded under and when that
 * version was last confirmed. Reads go:
 *
 * - no key (no session)         → load, uncached; Django answers 401 as ever.
 * - no entry                    → probe and load together, one round trip.
 * - confirmed within cooldown   → the entry, no calls at all.
 * - probe agrees                → the entry, confirmation renewed.
 * - probe disagrees             → drop, reload, store.
 * - probe fails with 401        → rethrow: the session is gone, say so.
 * - probe fails otherwise       → the entry, unconfirmed, so the next read
 *                                 probes again; with no entry, load uncached.
 *
 * An outage therefore never reads as "no data": a miss surfaces exactly the
 * problem it surfaces today. Pure apart from the injected functions.
 */
import { ProblemError } from '../core/problem'
import { TtlCache } from '../core/ttl-cache'

export interface SnapshotStoreOptions<T> {
  /** The current version of the data; cheap. */
  probe: () => Promise<string>
  /** The data itself; expensive. */
  load: () => Promise<T>
  /** How long a confirmed version is trusted without probing. */
  cooldownMs: number
  /** How long an entry may live regardless — the backstop for changes no probe explains. */
  ttlMs: number
  maxEntries: number
  now?: () => number
}

export interface SnapshotStore<T> {
  get(key: string | null): Promise<T>
  /** Forget one key, or everything. */
  invalidate(key?: string): void
}

interface Entry<T> {
  /** null when the probe failed alongside the load: never trusted, never kept. */
  version: string | null
  checkedAt: number
  value: T
}

function isUnauthorized(error: unknown): boolean {
  return error instanceof ProblemError && error.problem.status === 401
}

export function createSnapshotStore<T>({
  probe,
  load,
  cooldownMs,
  ttlMs,
  maxEntries,
  now = Date.now,
}: SnapshotStoreOptions<T>): SnapshotStore<T> {
  const cache = new TtlCache<Entry<T>>({ ttlMs, maxEntries, now })
  // One revalidation per key at a time, however many requests arrive past the cooldown.
  const revalidating = new Map<string, Promise<Entry<T>>>()

  async function cold(): Promise<Entry<T>> {
    const [version, value] = await Promise.all([
      probe().catch((error: unknown) => {
        if (isUnauthorized(error)) throw error
        return null
      }),
      load(),
    ])
    return { version, checkedAt: now(), value }
  }

  async function revalidate(key: string, entry: Entry<T>): Promise<Entry<T>> {
    let version: string
    try {
      version = await probe()
    } catch (error) {
      if (isUnauthorized(error)) throw error
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
    async get(key) {
      if (key === null) return load()
      const hit = cache.peek(key)
      if (!hit) {
        const entry = await cache.get(key, cold)
        if (entry.version === null) cache.delete(key)
        return entry.value
      }
      const entry = await hit
      if (now() - entry.checkedAt < cooldownMs) return entry.value
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

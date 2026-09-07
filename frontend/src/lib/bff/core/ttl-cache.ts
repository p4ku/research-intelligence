/**
 * A small promise cache with a time-to-live: the same key within `ttlMs`
 * shares one load (in flight or settled), a rejected load is forgotten so
 * the next caller retries, and the oldest key goes once `maxEntries` is
 * passed. Module-level instances live as long as the server process — the
 * right lifetime for a typeahead's corpus, the wrong one for anything a
 * page must see fresh. Pure; `now` is injectable for tests.
 */
export interface TtlCacheOptions {
  ttlMs: number
  maxEntries: number
  now?: () => number
}

interface Entry<T> {
  expires: number
  value: Promise<T>
}

export class TtlCache<T> {
  private readonly entries = new Map<string, Entry<T>>()
  private readonly ttlMs: number
  private readonly maxEntries: number
  private readonly now: () => number

  constructor({ ttlMs, maxEntries, now = Date.now }: TtlCacheOptions) {
    this.ttlMs = ttlMs
    this.maxEntries = maxEntries
    this.now = now
  }

  get(key: string, load: () => Promise<T>): Promise<T> {
    const at = this.now()
    const hit = this.entries.get(key)
    if (hit && hit.expires > at) return hit.value
    this.entries.delete(key)

    const value = load()
    const entry: Entry<T> = { expires: at + this.ttlMs, value }
    this.entries.set(key, entry)
    value.catch(() => {
      if (this.entries.get(key) === entry) this.entries.delete(key)
    })
    while (this.entries.size > this.maxEntries) {
      const oldest = this.entries.keys().next().value
      if (oldest === undefined) break
      this.entries.delete(oldest)
    }
    return value
  }

  clear(): void {
    this.entries.clear()
  }

  get size(): number {
    return this.entries.size
  }
}

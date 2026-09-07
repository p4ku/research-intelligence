/**
 * A small promise cache with a time-to-live: the same key within `ttlMs`
 * shares one load (in flight or settled), a rejected load is forgotten so
 * the next caller retries, and the least recently used key goes once
 * `maxEntries` is passed. Module-level instances live as long as the server process — the
 * right lifetime for the corpus snapshot (../corpus/snapshot.ts), whose
 * freshness is decided by a version probe, not by the ttl alone. Pure;
 * `now` is injectable for tests.
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
    const live = this.peek(key)
    if (live) return live
    const at = this.now()

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

  /**
   * The live load for a key, or undefined when absent or past its ttl. Never
   * loads. A hit moves the key to the back of the line, so eviction takes
   * the least recently used key rather than the oldest inserted.
   */
  peek(key: string): Promise<T> | undefined {
    const hit = this.entries.get(key)
    if (!hit) return undefined
    this.entries.delete(key)
    if (hit.expires <= this.now()) return undefined
    this.entries.set(key, hit)
    return hit.value
  }

  delete(key: string): void {
    this.entries.delete(key)
  }

  clear(): void {
    this.entries.clear()
  }

  get size(): number {
    return this.entries.size
  }
}

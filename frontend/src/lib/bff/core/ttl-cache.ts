/**
 * A small promise cache with a time-to-live: the same key within `ttlMs`
 * shares one load (in flight or settled), a rejected load is forgotten so
 * the next caller retries, and the least recently used key goes once
 * `maxEntries` — or, when the values are measured, `maxBytes` — is passed.
 * Module-level instances live as long as the server process — the right
 * lifetime for the corpus snapshot (../corpus/snapshot.ts), whose freshness
 * is decided by a version probe, not by the ttl alone. Pure; `now` is
 * injectable for tests.
 *
 * Bytes are counted once a load settles (an in-flight entry weighs nothing),
 * so the budget bounds what is retained, not what is being fetched. One entry
 * over the whole budget is still kept — it is served, and goes at the next
 * insert.
 */
export interface TtlCacheOptions<T> {
  ttlMs: number
  maxEntries: number
  /** Retained-size budget across every settled entry, in whatever unit `sizeOf` returns. */
  maxBytes?: number
  sizeOf?: (value: T) => number
  now?: () => number
}

interface Entry<T> {
  expires: number
  value: Promise<T>
  bytes: number
}

export class TtlCache<T> {
  private readonly entries = new Map<string, Entry<T>>()
  private readonly ttlMs: number
  private readonly maxEntries: number
  private readonly maxBytes: number
  private readonly sizeOf: (value: T) => number
  private readonly now: () => number
  private total = 0

  constructor({
    ttlMs,
    maxEntries,
    maxBytes = Number.POSITIVE_INFINITY,
    sizeOf = () => 0,
    now = Date.now,
  }: TtlCacheOptions<T>) {
    this.ttlMs = ttlMs
    this.maxEntries = maxEntries
    this.maxBytes = maxBytes
    this.sizeOf = sizeOf
    this.now = now
  }

  get(key: string, load: () => Promise<T>): Promise<T> {
    const live = this.peek(key)
    if (live) return live
    const at = this.now()

    const value = load()
    const entry: Entry<T> = { expires: at + this.ttlMs, value, bytes: 0 }
    this.entries.set(key, entry)
    value.then(
      (settled) => {
        // Only an entry still in the map is weighed: one dropped mid-load
        // (invalidated, evicted, expired) must not count against the budget.
        if (this.entries.get(key) !== entry) return
        entry.bytes = this.sizeOf(settled)
        this.total += entry.bytes
        this.trim(key)
      },
      () => {
        if (this.entries.get(key) === entry) this.drop(key)
      },
    )
    this.trim(key)
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
    if (hit.expires <= this.now()) {
      this.total -= hit.bytes
      return undefined
    }
    this.entries.set(key, hit)
    return hit.value
  }

  delete(key: string): void {
    this.drop(key)
  }

  clear(): void {
    this.entries.clear()
    this.total = 0
  }

  get size(): number {
    return this.entries.size
  }

  /** Retained bytes across settled entries. */
  get bytes(): number {
    return this.total
  }

  private drop(key: string): void {
    const entry = this.entries.get(key)
    if (!entry) return
    this.entries.delete(key)
    this.total -= entry.bytes
  }

  /** Evict least recently used keys until both limits hold, never `keep`. */
  private trim(keep: string): void {
    for (const key of this.entries.keys()) {
      if (this.entries.size <= this.maxEntries && this.total <= this.maxBytes) return
      if (key === keep) continue
      this.drop(key)
    }
  }
}

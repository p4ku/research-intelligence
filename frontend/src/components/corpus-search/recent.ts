/**
 * Recent searches, per browser (not per user — it is a convenience, not a
 * record). Every storage call is guarded: private windows, quota and
 * blocked site data all read as "nothing remembered". Pure given a store.
 */
export const RECENT_KEY = 'rs-search-recent'
export const RECENT_MAX = 5

export type RecentStore = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

function browserStore(): RecentStore | undefined {
  try {
    return globalThis.localStorage
  } catch {
    return undefined
  }
}

export function readRecent(store: RecentStore | undefined = browserStore()): string[] {
  try {
    const raw = store?.getItem(RECENT_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((x): x is string => typeof x === 'string').slice(0, RECENT_MAX)
  } catch {
    return []
  }
}

/** Remember a query at the front (case-insensitively deduped); returns the new list. */
export function pushRecent(q: string, store: RecentStore | undefined = browserStore()): string[] {
  const query = q.trim()
  const current = readRecent(store)
  if (!query) return current
  const next = [
    query,
    ...current.filter((item) => item.toLowerCase() !== query.toLowerCase()),
  ].slice(0, RECENT_MAX)
  try {
    store?.setItem(RECENT_KEY, JSON.stringify(next))
  } catch {
    // Nothing to do: the list still applies for this page.
  }
  return next
}

export function clearRecent(store: RecentStore | undefined = browserStore()): void {
  try {
    store?.removeItem(RECENT_KEY)
  } catch {
    // Nothing to do.
  }
}

/**
 * Ordering ISO instants the way Django writes them. Two things make the raw
 * strings unsortable: DRF omits the fraction when the microseconds are zero
 * (`…T10:00:00Z` sorts after `…T10:00:00.4Z`, since 'Z' > '.'), and offsets
 * vary. Two things make `Date.parse` alone insufficient: it truncates to
 * milliseconds while `auto_now_add` keeps microseconds, so a step retried
 * 400µs later would tie. Pure.
 */

/** Digits past the millisecond, as a number; 0 without a fraction. */
function subMillis(iso: string): number {
  const digits = /\.(\d+)/.exec(iso)?.[1] ?? ''
  return Number(digits.padEnd(9, '0').slice(3))
}

/**
 * Earlier first. Unparseable on either side compares as 0, so a caller can
 * fall through to its own tiebreak (`if (d) return d`).
 */
export function compareInstants(a: string, b: string): number {
  const d = Date.parse(a) - Date.parse(b)
  if (d) return Number.isNaN(d) ? 0 : d
  return subMillis(a) - subMillis(b)
}

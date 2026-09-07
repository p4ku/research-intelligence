/**
 * The time window a capped paper list covers. Extractions are written after
 * their paper (`auto_now_add` on both, never rewritten), so every extraction
 * of a kept paper is at least as new as the oldest kept paper: draining
 * extractions newest-first down to that instant reaches all of them, and
 * nothing older can belong to a kept paper. Instants are compared as
 * numbers — DRF omits the fraction when the microseconds are zero, so the
 * strings themselves do not sort. Pure.
 */
export function extractionCutoff(papers: readonly { created_at: string }[]): number | null {
  let oldest: number | null = null
  for (const { created_at } of papers) {
    const at = Date.parse(created_at)
    if (Number.isNaN(at)) continue
    if (oldest === null || at < oldest) oldest = at
  }
  return oldest
}

/** What the cap dropped, if anything: only a walk that reached the cap can have. */
export function truncation(
  kept: number,
  total: number,
  cap: number,
): { kept: number; total: number } | undefined {
  return kept >= cap && total > kept ? { kept, total } : undefined
}

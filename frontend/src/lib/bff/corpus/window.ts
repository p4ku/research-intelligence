/**
 * The time window a capped paper list covers. Extractions are written after
 * their paper, so every extraction of a kept paper is at least as new as the
 * oldest kept paper: draining extractions newest-first down to that instant
 * reaches all of them, and nothing older can belong to a kept paper. Pure.
 */
export function extractionCutoff(papers: readonly { created_at: string }[]): string | null {
  let oldest: string | null = null
  for (const { created_at } of papers) {
    if (oldest === null || created_at < oldest) oldest = created_at
  }
  return oldest
}

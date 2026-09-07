/**
 * The user's corpus for the typeahead and the Ask picker.
 *
 * The raw lists behind `papers.listEverywhere()` are held across requests
 * by the corpus snapshot (../corpus/snapshot.ts), so scoring the corpus
 * again per keystroke costs microseconds and needs no cache of its own.
 * The client side still holds one settled palette per tab for a short
 * while (ask/use-palette.ts, mirroring CORPUS_TTL_MS).
 *
 * Server-only.
 */
import 'server-only'

import { invalidateCorpusSnapshot } from '../corpus/snapshot'
import { papers, type CorpusPapers } from './service'

/** How long the browser may keep a palette before asking again. */
export const CORPUS_TTL_MS = 45_000

/** The user's corpus, scored from the snapshot. */
export async function recentCorpus(): Promise<CorpusPapers> {
  return papers.listEverywhere()
}

/** Forget every cached corpus — a run just started, so every member's corpus is about to change. */
export function invalidateRecentCorpus(): void {
  invalidateCorpusSnapshot()
}

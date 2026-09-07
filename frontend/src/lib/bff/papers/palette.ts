/**
 * The corpus → the Ask picker's rows: a slim projection of the papers the
 * reader's text matches, best first, at most `limit` of them. The matcher
 * is the one behind Home's typeahead and the Papers page, so what the
 * picker offers is what a search would have found. Pure.
 */
import { byValueDesc } from '@/lib/papers/select'
import { parseQuery, rankAll } from '@/lib/search/match'
import type { Palette, PaletteEntry, PaletteQuery, ScoredPaper } from './schema'

export function toPaletteEntry(p: ScoredPaper): PaletteEntry {
  return {
    id: p.id,
    title: p.title,
    first_author: p.authors[0] ?? null,
    source: p.source,
    signal_score: p.signal_score,
    created_at: p.created_at,
  }
}

export function toPalette(
  { papers }: { papers: ScoredPaper[] },
  { q, limit }: PaletteQuery = { q: '', limit: 20 },
): Palette {
  const ranked = q
    ? rankAll(papers, parseQuery(q)).map((r) => r.paper)
    : [...papers].sort((a, b) => byValueDesc(a.signal_score, b.signal_score))
  return {
    query: q,
    papers: ranked.slice(0, limit).map(toPaletteEntry),
    matched: ranked.length,
    total: papers.length,
  }
}

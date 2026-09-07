/** The corpus → the Ask picker's rows: a slim projection, best signal first. Pure. */
import { byValueDesc } from '@/lib/papers/select'
import type { Palette, PaletteEntry, ScoredPaper } from './schema'

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

export function toPalette({ papers }: { papers: ScoredPaper[] }): Palette {
  return {
    papers: papers.map(toPaletteEntry).sort((a, b) => byValueDesc(a.signal_score, b.signal_score)),
  }
}

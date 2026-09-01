/**
 * Inline citation markers the chat model writes into answers, e.g.
 * `[Page 7, Fig 4b, box_2d: [320, 150, 680, 890], quote: "…"]`. The backend
 * parses these into `visual_citations` but leaves the marker text in the
 * answer (chat/engine/citations.py only reads them), so the frontend turns
 * them into citation chips. Pure string work, no React — unit-tested.
 */
import type { VisualCitation } from '@/lib/bff/chat/schema'

export interface CitationRef {
  page: number
  label?: string
  box?: number[]
  quote?: string
}

/**
 * Mirrors the backend's pattern (citations.py:52), anchored on `Page` so bare
 * references like `[1]` or `[Smith 2020]` never match. The label is lazy so it
 * stops before `, box_2d` / `, quote`; the quote is `[^"]+` and `]` must
 * follow immediately — the same acceptance set the backend has.
 */
export const MARKER_RE =
  /\[Page\s*(\d+)(?:,\s*([A-Za-z0-9\s._-]+?))?(?:,\s*box_2d:\s*\[([0-9,\s]+)\])?(?:,\s*quote:\s*"([^"]+)")?\]/gi

// Private-use chars: no markdown-significant characters, so a placeholder
// survives parsing inside bold, list items and table cells intact.
const PLACEHOLDER_OPEN = '\uE001'
const PLACEHOLDER_CLOSE = '\uE002'
export const PLACEHOLDER_RE = /\uE001(\d+)\uE002/

/**
 * Replace each marker with `\uE001<index>\uE002`, where index points into
 * `refs`. Duplicates collapse to one ref (key = page|label|box|quote — the
 * backend dedupes by dict equality), so ordinal matching against
 * `visual_citations` holds.
 */
export function extractCitationMarkers(text: string): { text: string; refs: CitationRef[] } {
  const refs: CitationRef[] = []
  const indexByKey = new Map<string, number>()
  const replaced = text.replace(
    MARKER_RE,
    (_match, page: string, label?: string, box?: string, quote?: string) => {
      const ref: CitationRef = { page: Number(page) }
      const trimmedLabel = label?.trim()
      if (trimmedLabel) ref.label = trimmedLabel
      if (box) ref.box = (box.match(/\d+/g) ?? []).map(Number)
      const trimmedQuote = quote?.trim()
      if (trimmedQuote) ref.quote = trimmedQuote
      const key = `${ref.page}|${ref.label ?? ''}|${ref.box?.join(',') ?? ''}|${ref.quote ?? ''}`
      let index = indexByKey.get(key)
      if (index === undefined) {
        index = refs.push(ref) - 1
        indexByKey.set(key, index)
      }
      return `${PLACEHOLDER_OPEN}${index}${PLACEHOLDER_CLOSE}`
    },
  )
  return { text: replaced, refs }
}

// A trailing `[`, `[P`, `[Pa`, `[Pag` may be the first frame of a marker.
const PARTIAL_PREFIX_RE = /\s?\[(?:P(?:a(?:g)?)?)?$/i

/**
 * While streaming, hide a marker that has started but not yet closed so the
 * transcript never flashes half a `[Page 7, Fig 4b, box_2d: [320, …`. Tracks
 * bracket depth (the box is nested) and skips brackets inside the quote.
 */
export function holdBackOpenMarker(text: string): string {
  const start = text.toLowerCase().lastIndexOf('[page')
  if (start === -1) return text.replace(PARTIAL_PREFIX_RE, '')
  let depth = 0
  let inQuote = false
  for (let i = start; i < text.length; i++) {
    const ch = text[i]
    if (ch === '"') inQuote = !inQuote
    else if (inQuote) continue
    else if (ch === '[') depth++
    else if (ch === ']' && --depth === 0) return text
  }
  return text.slice(0, start).replace(/\s$/, '')
}

/**
 * Pair each ref with its structured citation: by position when the backend
 * emitted one entry per distinct marker (the normal case), else by content.
 */
export function matchCitations(
  refs: CitationRef[],
  citations: VisualCitation[],
): (VisualCitation | null)[] {
  if (refs.length === citations.length) return refs.map((_, i) => citations[i])
  const used = new Set<number>()
  return refs.map((ref) => {
    const i = citations.findIndex(
      (c, idx) =>
        !used.has(idx) &&
        c.page === ref.page &&
        (c.label ?? '') === (ref.label ?? '') &&
        (!ref.quote || !c.quote || c.quote === ref.quote),
    )
    if (i === -1) return null
    used.add(i)
    return citations[i]
  })
}

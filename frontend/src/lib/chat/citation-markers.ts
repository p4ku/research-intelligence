/**
 * Inline citation markers the chat model writes into answers, e.g.
 * `[Page 7, Fig 4b, box_2d: [320, 150, 680, 890], quote: "…"]`. The backend
 * parses these into `visual_citations` but leaves the marker text in the
 * answer (chat/engine/citations.py only reads them), so the frontend turns
 * them into citation chips. Pure string work, no React — unit-tested.
 */
import type { VisualCitation } from '@/lib/bff/chat/schema'

export interface CitationRef {
  /** Absent on the OCR-markdown path, which carries no page numbers. */
  page?: number
  label?: string
  box?: number[]
  quote?: string
}

/**
 * Mirrors the backend's pattern (citations.py). Two forms: page-led
 * `[Page 7, Fig 4b, box_2d: […], quote: "…"]` with everything after the page
 * optional, and page-less `[Fig 4b, quote: "…"]` / `[quote: "…"]` where the
 * quote is required. A marker needs a page or a quote, so bare references
 * like `[1]` or `[Smith 2020]` never match. Labels are lazy so they stop
 * before `, box_2d` / `, quote`; the quote is `[^"]+` and `]` must follow
 * immediately — the same acceptance set the backend has.
 */
export const MARKER_RE =
  /\[(?:Page\s*(\d+)(?:,\s*([A-Za-z0-9\s._-]+?))?(?:,\s*box_2d:\s*\[([0-9,\s]+)\])?(?:,\s*quote:\s*"([^"]+)")?|(?:([A-Za-z0-9\s._-]+?),\s*)?(?:box_2d:\s*\[([0-9,\s]+)\],\s*)?quote:\s*"([^"]+)")\]/gi

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
    (
      _match,
      page?: string,
      labelA?: string,
      boxA?: string,
      quoteA?: string,
      labelB?: string,
      boxB?: string,
      quoteB?: string,
    ) => {
      const ref: CitationRef = {}
      if (page) ref.page = Number(page)
      const trimmedLabel = (labelA ?? labelB)?.trim()
      if (trimmedLabel) ref.label = trimmedLabel
      const box = boxA ?? boxB
      if (box) ref.box = (box.match(/\d+/g) ?? []).map(Number)
      const trimmedQuote = (quoteA ?? quoteB)?.trim()
      if (trimmedQuote) ref.quote = trimmedQuote
      const key = `${ref.page ?? ''}|${ref.label ?? ''}|${ref.box?.join(',') ?? ''}|${ref.quote ?? ''}`
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

/**
 * Could this unclosed bracket's own body (up to the next `[`) still become a
 * marker? `Page…` always can; so can anything that already names a
 * `quote:`/`box_2d:` field; and a label-looking prefix (`Fig 4b, quo`) can
 * too. A half-open interval like `[0, 1)`, an index like `w[i`, or prose that
 * has run on past 120 characters cannot, so those stay visible.
 */
function mayBecomeMarker(body: string): boolean {
  if (/^page\b/i.test(body)) return true
  if (/(?:^|,)\s*(?:quote|box_2d)\s*:/i.test(body)) return true
  return body.length <= 120 && /^[A-Za-z0-9\s._-]*(?:,\s*[a-z_0-9]*)?$/i.test(body)
}

// A marker's quote opens right after `quote:`; only that `"` starts a span in
// which brackets are ignored. Prose quotes never toggle anything.
const QUOTE_OPENS_RE = /quote:\s*$/i

/**
 * While streaming, hide a marker that has started but not yet closed so the
 * transcript never flashes half a `[Page 7, Fig 4b, box_2d: [320, …`. Tracks
 * bracket depth (the box is nested) and skips brackets inside a marker quote.
 * Cuts at the outermost open bracket whose own body can still turn into a
 * marker; stray `[` before it (intervals, code indices) are left alone, and
 * their body is judged only up to the next `[`, so a real marker later in the
 * text never makes an earlier stray bracket look like one.
 */
export function holdBackOpenMarker(text: string): string {
  const open: number[] = []
  let inQuote = false
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (inQuote) {
      if (ch === '"') inQuote = false
    } else if (ch === '"') {
      if (open.length > 0 && QUOTE_OPENS_RE.test(text.slice(open[open.length - 1], i))) {
        inQuote = true
      }
    } else if (ch === '[') open.push(i)
    else if (ch === ']' && open.length > 0) open.pop()
  }
  for (const start of open) {
    const next = text.indexOf('[', start + 1)
    const end = next === -1 ? text.length : next
    if (mayBecomeMarker(text.slice(start + 1, end))) {
      return text.slice(0, start).replace(/\s$/, '')
    }
  }
  return text
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
        (c.page ?? null) === (ref.page ?? null) &&
        (c.label ?? '') === (ref.label ?? '') &&
        (!ref.quote || !c.quote || c.quote === ref.quote),
    )
    if (i === -1) return null
    used.add(i)
    return citations[i]
  })
}

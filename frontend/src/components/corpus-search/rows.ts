/**
 * What the panel shows for a response — the intent decides the order:
 *
 * - text:      Papers (+ "See all N") → Domains → Ask about the top hit
 * - question:  Ask first → Papers → Domains
 * - id:        one "Open paper" row (+ Ask), or an honest miss
 * - nothing typed: Recent searches → Try (the domain's own scan topics)
 *
 * Pure; `t` comes in so the strings are counted by the i18n audit.
 */
import type { SearchHit, SearchResponse } from '@/lib/bff/search/schema'
import { fmt, type T } from '@/lib/i18n'
import { shortTitle } from '@/lib/papers/select'

export type Row =
  | { kind: 'paper'; id: string; href: string; hit: SearchHit }
  | { kind: 'more'; id: 'more'; href: string; total: number }
  | { kind: 'domain'; id: string; href: string; name: string; matched: number }
  | { kind: 'ask'; id: 'ask'; href: string; label: string }
  | { kind: 'papers'; id: 'papers'; href: string }
  | { kind: 'recent'; id: string; q: string }
  | { kind: 'try'; id: string; q: string }

export type SectionKey = 'exact' | 'ask' | 'papers' | 'domains' | 'recent' | 'try' | 'note'

export interface Section {
  key: SectionKey
  label: string | null
  /** A quiet one-liner instead of rows (a miss, an outage). */
  note?: string
  rows: Row[]
}

export interface RowContext {
  q: string
  recent: string[]
  suggestions: string[]
  error: boolean
  t: T
}

export const papersHref = (q: string) =>
  q.trim() ? `/papers?q=${encodeURIComponent(q.trim())}` : '/papers'

export const rowId = (row: Row) => `cs-${row.kind}-${row.id}`

export const flatten = (sections: Section[]): Row[] => sections.flatMap((s) => s.rows)

/** Rows that navigate somewhere (the others rewrite the query). */
export function rowHref(row: Row): string | null {
  return 'href' in row ? row.href : null
}

const openPapers = (): Section => ({
  key: 'papers',
  label: null,
  rows: [{ kind: 'papers', id: 'papers', href: '/papers' }],
})

function askSection(result: SearchResponse, t: T): Section | null {
  const top = result.papers[0]
  if (!result.ask || !top) return null
  return {
    key: 'ask',
    label: null,
    rows: [
      {
        kind: 'ask',
        id: 'ask',
        href: result.ask.href,
        label: fmt(t('Ask about “{title}”'), { title: askTitle(top.title) }),
      },
    ],
  }
}

function paperSection(result: SearchResponse, t: T): Section | null {
  if (result.papers.length === 0) return null
  const rows: Row[] = result.papers.map((hit) => ({
    kind: 'paper',
    id: hit.id,
    href: `/papers/${hit.id}`,
    hit,
  }))
  if (result.papers_total > result.papers.length) {
    rows.push({
      kind: 'more',
      id: 'more',
      href: papersHref(result.query),
      total: result.papers_total,
    })
  }
  return { key: 'papers', label: t('Papers'), rows }
}

function domainSection(result: SearchResponse, t: T): Section | null {
  if (result.domains.length === 0) return null
  return {
    key: 'domains',
    label: t('Domains'),
    rows: result.domains.map((d) => ({
      kind: 'domain',
      id: d.id,
      href: d.latest_edition?.href ?? '/briefing',
      name: d.name,
      matched: d.papers_matched,
    })),
  }
}

function idleSections({ recent, suggestions, t }: RowContext): Section[] {
  const sections: Section[] = []
  if (recent.length > 0) {
    sections.push({
      key: 'recent',
      label: t('Recent'),
      rows: recent.map((q) => ({ kind: 'recent', id: q, q })),
    })
  }
  // A topic already in Recent is not a suggestion any more.
  const seen = new Set(recent.map((q) => q.toLowerCase()))
  const fresh = suggestions.filter((q) => !seen.has(q.toLowerCase()))
  if (fresh.length > 0) {
    sections.push({
      key: 'try',
      label: t('Try'),
      rows: fresh.map((q) => ({ kind: 'try', id: q, q })),
    })
  }
  return sections
}

/** A title short enough to sit in one row: up to its colon, then at most ~60 characters at a word. */
export function askTitle(title: string, max = 60): string {
  const short = shortTitle(title)
  if (short.length <= max) return short
  const cut = short.lastIndexOf(' ', max)
  return `${short.slice(0, cut > max / 2 ? cut : max).trimEnd()}…`
}

export function buildSections(result: SearchResponse | null, ctx: RowContext): Section[] {
  const { q, error, t } = ctx
  const typed = q.trim().length >= 2

  if (!result || result.intent === 'empty') {
    if (typed && error) {
      return [
        {
          key: 'note',
          label: null,
          note: t('Search is unavailable — press Enter to open Papers.'),
          rows: [],
        },
        openPapers(),
      ]
    }
    return typed ? [] : idleSections(ctx)
  }

  const stale: Section[] = error
    ? [
        {
          key: 'note',
          label: null,
          note: t('Search is unavailable — press Enter to open Papers.'),
          rows: [],
        },
      ]
    : []

  if (result.intent === 'id') {
    const hit = result.papers[0]
    if (result.exact && hit) {
      const sections: Section[] = [
        {
          key: 'exact',
          label: t('Open paper'),
          rows: [{ kind: 'paper', id: hit.id, href: `/papers/${hit.id}`, hit }],
        },
      ]
      const ask = askSection(result, t)
      if (ask) sections.push(ask)
      return [...stale, ...sections]
    }
    return [
      ...stale,
      { key: 'note', label: null, note: t('No paper with that id in your corpus.'), rows: [] },
      openPapers(),
    ]
  }

  const papers = paperSection(result, t)
  const domains = domainSection(result, t)
  const ask = askSection(result, t)
  if (!papers && !domains) {
    return [
      ...stale,
      {
        key: 'note',
        label: null,
        note: fmt(t('No papers match “{q}”.'), { q: result.query }),
        rows: [],
      },
      openPapers(),
    ]
  }
  const ordered = result.intent === 'question' ? [ask, papers, domains] : [papers, domains, ask]
  return [...stale, ...ordered.filter((s): s is Section => s !== null)]
}

/**
 * The one matcher every search surface shares — the Home typeahead, the
 * `/bff/papers?search=` face and the Papers page filter — so what the
 * dropdown shows is what Papers lands on. Pure and isomorphic: no server
 * imports, no React, no zod.
 *
 * Reading a query the way a researcher typed it:
 * - words match whole or as prefixes ("coord" → Coordinated), every word
 *   must land somewhere (AND), and hyphens are spaces ("solid state" ≡
 *   "solid-state"; "multiagent" also hits "Multi-Agent");
 * - a title hit outranks an author hit outranks an abstract hit, and the
 *   signal score only breaks ties;
 * - an arXiv id, a DOI, or a pasted arxiv.org / doi.org URL is an `id`
 *   intent — open that paper, don't search for it;
 * - a question mark or an opening "what / which / how / welche …" is a
 *   `question` intent — offer Ask first.
 */
import type { ScoredPaper } from '@/lib/bff/papers/schema'

export type Field = 'title' | 'authors' | 'abstract' | 'id'
export type IdKind = 'arxiv' | 'doi'

export interface IdRef {
  kind: IdKind
  /** Canonical form: arXiv without version, DOI lowercased. */
  value: string
  /** The external landing page for the id. */
  url: string
}

export type Intent =
  | { kind: 'empty' }
  | { kind: 'id'; id: IdRef }
  | { kind: 'question'; tokens: string[] }
  | { kind: 'text'; tokens: string[] }

export interface Query {
  raw: string
  normalized: string
  tokens: string[]
  intent: Intent
}

export interface Hit {
  score: number
  /** Fields that carried at least one token, in title → authors → abstract → id order. */
  matched: Field[]
}

export interface Segment {
  text: string
  hit: boolean
}

/** The subset the matcher reads; a ScoredPaper passes unchanged. */
export type Searchable = Pick<
  ScoredPaper,
  'title' | 'authors' | 'abstract' | 'arxiv_id' | 'doi' | 'signal_score'
>

const DASHES = /[-–—_]/g
const WORD_BREAK = /[^\p{L}\p{N}]+/u
const HYPHENATED = /[\p{L}\p{N}]+(?:[-–—_][\p{L}\p{N}]+)+/gu

/** Lowercase, diacritics stripped, dashes as spaces, whitespace collapsed. */
export function normalize(text: string): string {
  return text
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
    .replace(DASHES, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

/** Words of at least two characters. */
export function tokenize(text: string): string[] {
  return normalize(text)
    .split(WORD_BREAK)
    .filter((token) => token.length >= 2)
    .map(stem)
}

/**
 * Just enough stemming that "agents" finds "Multi-Agent" and "batteries"
 * finds "battery": a trailing plural s (not ss) and ies → y. Applied to
 * both sides, so it is a comparison rule rather than a vocabulary.
 */
export function stem(word: string): string {
  if (word.length >= 5 && word.endsWith('ies')) return `${word.slice(0, -3)}y`
  if (word.length >= 4 && word.endsWith('s') && !word.endsWith('ss')) return word.slice(0, -1)
  return word
}

/** Field words plus the joined form of every hyphenated run ("multi-agent" → also "multiagent"). */
function fieldTokens(text: string): string[] {
  const tokens = tokenize(text)
  const plain = text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase()
  for (const run of plain.match(HYPHENATED) ?? []) tokens.push(run.replace(DASHES, ''))
  return tokens
}

const ARXIV_NEW = /^(\d{4}\.\d{4,5})(?:v\d+)?$/i
const ARXIV_OLD = /^([a-z-]+(?:\.[a-z]{2})?\/\d{7})(?:v\d+)?$/i
const DOI = /^(10\.\d{4,9}\/\S+)$/i
const ARXIV_URL = /^https?:\/\/(?:www\.)?arxiv\.org\/(?:abs|pdf)\/([^?#]+?)(?:\.pdf)?\/?$/i
const DOI_URL = /^https?:\/\/(?:dx\.)?doi\.org\/(.+)$/i

/** An arXiv id, a DOI, or a URL carrying one; null for anything with a space in it. */
export function detectId(raw: string): IdRef | null {
  let s = raw.trim()
  if (!s || /\s/.test(s)) return null
  s = s.replace(/^(?:arxiv|doi):/i, '')
  const asArxivUrl = ARXIV_URL.exec(s)
  if (asArxivUrl) s = asArxivUrl[1]!
  const asDoiUrl = DOI_URL.exec(s)
  if (asDoiUrl) s = asDoiUrl[1]!

  const doi = DOI.exec(s)
  if (doi) {
    const value = doi[1]!.toLowerCase()
    return { kind: 'doi', value, url: `https://doi.org/${value}` }
  }
  const arxiv = ARXIV_NEW.exec(s) ?? ARXIV_OLD.exec(s)
  if (arxiv) {
    const value = arxiv[1]!.toLowerCase()
    return { kind: 'arxiv', value, url: `https://arxiv.org/abs/${value}` }
  }
  return null
}

const QUESTION_WORDS = new Set([
  ...['what', 'which', 'how', 'why', 'who', 'whom', 'whose', 'when', 'where'],
  ...['is', 'are', 'does', 'do', 'did', 'can', 'could', 'should', 'would', 'will'],
  ...['has', 'have', 'was', 'were'],
  ...['welche', 'welcher', 'welches', 'wie', 'warum', 'wer', 'wann', 'wo', 'wieso'],
  ...['ist', 'sind', 'kann', 'sollte', 'gibt', 'hat', 'haben'],
])

/**
 * Words that carry no topic: never required to appear in a paper. A query
 * made only of these keeps them, so "what is new" still matches something.
 */
const STOPWORDS = new Set([
  ...QUESTION_WORDS,
  ...['the', 'an', 'of', 'in', 'on', 'for', 'and', 'or', 'to', 'with', 'at', 'by', 'from'],
  ...['about', 'into', 'over', 'any', 'all', 'there', 'that', 'this', 'these', 'those', 'it'],
  ...['paper', 'papers', 'research', 'study', 'studies', 'we', 'our', 'you', 'they', 'me'],
  ...['der', 'die', 'das', 'ein', 'eine', 'und', 'oder', 'zu', 'mit', 'von', 'im', 'am', 'es'],
  ...['uber', 'fur', 'auf', 'aus', 'bei', 'nach', 'zum', 'zur', 'den', 'dem', 'des'],
])

/** A trailing "?" or an opening interrogative (EN or DE). Word count alone never makes a question. */
export function isQuestion(raw: string, tokens: string[]): boolean {
  if (raw.trim().endsWith('?')) return true
  const first = tokens[0]
  return first !== undefined && QUESTION_WORDS.has(first)
}

export function parseQuery(raw: string): Query {
  const trimmed = raw.trim()
  if (!trimmed) return { raw, normalized: '', tokens: [], intent: { kind: 'empty' } }
  const id = detectId(trimmed)
  if (id) return { raw, normalized: id.value, tokens: [id.value], intent: { kind: 'id', id } }
  const normalized = normalize(trimmed)
  const words = tokenize(trimmed)
  if (words.length === 0) return { raw, normalized, tokens: [], intent: { kind: 'empty' } }
  const kind = isQuestion(trimmed, words) ? 'question' : 'text'
  const content = words.filter((w) => !STOPWORDS.has(w))
  const tokens = content.length > 0 ? content : words
  return { raw, normalized, tokens, intent: { kind, tokens } }
}

const WEIGHT = {
  title: { exact: 1.0, prefix: 0.85 },
  authors: { exact: 0.7, prefix: 0.6 },
  abstract: { exact: 0.45, prefix: 0.35 },
  id: 0.3,
} as const

/** Prefixes on the abstract need four characters — "stu" must not light up every "study". */
const ABSTRACT_PREFIX_MIN = 4

function best(
  token: string,
  field: string[],
  weights: { exact: number; prefix: number },
  prefixMin = 2,
): number {
  let score = 0
  for (const word of field) {
    if (word === token) return weights.exact
    if (token.length >= prefixMin && word.startsWith(token)) score = weights.prefix
  }
  return score
}

/**
 * Relevance of one paper for a parsed query, or null when a token finds no
 * home. Title > authors > abstract > ids; the whole query as a phrase in the
 * title and a title that opens with the first word earn bonuses; the signal
 * score contributes at most 0.1 so it only ever breaks ties.
 */
export function rank(paper: Searchable, query: Query, { relaxed = false } = {}): Hit | null {
  const { tokens } = query
  if (query.intent.kind === 'empty' || tokens.length === 0) return null
  // Strict: every word lands. Relaxed: at least half do, and misses cost score.
  const required = relaxed ? Math.max(1, Math.ceil(tokens.length / 2)) : tokens.length
  let hits = 0

  const title = fieldTokens(paper.title)
  const authors = fieldTokens(paper.authors.join(' '))
  const abstract = fieldTokens(paper.abstract)
  const ids = [paper.arxiv_id, paper.doi]
    .filter((id): id is string => !!id)
    .map((id) => id.toLowerCase())

  const matched = new Set<Field>()
  let sum = 0
  let titleHits = 0
  for (const token of tokens) {
    const byField: Record<Field, number> = {
      title: best(token, title, WEIGHT.title),
      authors: best(token, authors, WEIGHT.authors),
      abstract: best(token, abstract, WEIGHT.abstract, ABSTRACT_PREFIX_MIN),
      id: ids.some((id) => id.includes(token)) ? WEIGHT.id : 0,
    }
    let top = 0
    for (const field of ['title', 'authors', 'abstract', 'id'] as const) {
      const weight = byField[field]
      if (weight > 0) matched.add(field)
      if (weight > top) top = weight
    }
    if (top === 0) continue
    hits += 1
    if (byField.title > 0) titleHits += 1
    sum += top
  }
  if (hits < required) return null

  const normalizedTitle = normalize(paper.title)
  // A phrase is two or more words in the typed order; one word is just a hit.
  const phrase = tokens.length >= 2 && normalizedTitle.includes(query.normalized) ? 1 : 0
  const titleStart = normalizedTitle.startsWith(tokens[0]!) ? 1 : 0
  const score =
    (100 * sum) / tokens.length +
    15 * phrase +
    5 * titleStart +
    (10 * titleHits) / tokens.length +
    (paper.signal_score ?? 0) / 1000

  return {
    score,
    matched: (['title', 'authors', 'abstract', 'id'] as const).filter((f) => matched.has(f)),
  }
}

export interface Ranked<T> {
  paper: T
  hit: Hit
}

/**
 * Every paper that answers the query, best first. Strict first; when a
 * question or a multi-word query finds nothing that way, relaxed — a
 * question's words are rarely all in one paper, and "solid state battery
 * recycling" should still surface the solid-state battery papers.
 */
export function rankAll<T extends Searchable>(papers: readonly T[], query: Query): Ranked<T>[] {
  const pass = (relaxed: boolean): Ranked<T>[] => {
    const out: Ranked<T>[] = []
    for (const paper of papers) {
      const hit = rank(paper, query, { relaxed })
      if (hit) out.push({ paper, hit })
    }
    return out
  }
  let ranked = query.intent.kind === 'question' ? pass(true) : pass(false)
  if (ranked.length === 0 && query.tokens.length >= 2) ranked = pass(true)
  return ranked.sort((a, b) => b.hit.score - a.hit.score)
}

/* --------------------------- Highlight & snippet -------------------------- */

interface Mapped {
  /** The normalised text (same rules as normalize(), whitespace kept 1:1). */
  text: string
  /** For each normalised char, the [start, end) of the original char it came from. */
  spans: Array<[number, number]>
}

/** Normalise char by char so hits map back onto the original casing and diacritics. */
function mapNormalized(text: string): Mapped {
  let out = ''
  const spans: Array<[number, number]> = []
  let offset = 0
  for (const ch of text) {
    const start = offset
    offset += ch.length
    const normalized = ch.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().replace(DASHES, ' ')
    for (let i = 0; i < normalized.length; i += 1) {
      out += normalized[i]
      spans.push([start, offset])
    }
  }
  return { text: out, spans }
}

const isWordChar = (ch: string | undefined): boolean => ch !== undefined && /[\p{L}\p{N}]/u.test(ch)

/** Normalised [start, end) ranges where a token opens a word, extended to the word's end. */
function findHits(mapped: Mapped, tokens: string[]): Array<[number, number]> {
  const ranges: Array<[number, number]> = []
  const { text } = mapped
  const wanted = tokens.filter(Boolean)
  if (wanted.length === 0) return ranges
  // Walk the words; a word is a hit when its stem is, or begins with, a token
  // — the same rule rank() applies, so what matched is what lights up.
  let at = 0
  while (at < text.length) {
    if (!isWordChar(text[at])) {
      at += 1
      continue
    }
    let end = at
    while (isWordChar(text[end])) end += 1
    const word = stem(text.slice(at, end))
    if (wanted.some((token) => word === token || word.startsWith(token))) ranges.push([at, end])
    at = end
  }
  ranges.sort((a, b) => a[0] - b[0])
  const merged: Array<[number, number]> = []
  for (const range of ranges) {
    const last = merged[merged.length - 1]
    // One separator between two hits ("Multi-Agent", "cold chain") reads as one hit.
    if (last && range[0] <= last[1] + 1) last[1] = Math.max(last[1], range[1])
    else merged.push([range[0], range[1]])
  }
  return merged
}

/** The original text split into hit / non-hit segments for the query's tokens. */
export function highlight(text: string, tokens: string[]): Segment[] {
  if (!text) return []
  const mapped = mapNormalized(text)
  const hits = findHits(mapped, tokens)
  if (hits.length === 0) return [{ text, hit: false }]
  const segments: Segment[] = []
  let cursor = 0
  for (const [start, end] of hits) {
    const from = mapped.spans[start]![0]
    const to = mapped.spans[end - 1]![1]
    if (from > cursor) segments.push({ text: text.slice(cursor, from), hit: false })
    segments.push({ text: text.slice(from, to), hit: true })
    cursor = to
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), hit: false })
  return segments
}

/**
 * A window of the original text around the first hit (or its head when
 * nothing hits), cut at word boundaries, "…" on whichever side was trimmed.
 */
export function snippet(text: string, tokens: string[], maxLen = 160): string {
  if (text.length <= maxLen) return text
  const mapped = mapNormalized(text)
  const first = findHits(mapped, tokens)[0]
  const hitStart = first ? mapped.spans[first[0]]![0] : 0
  const hitEnd = first ? mapped.spans[first[1] - 1]![1] : 0

  let start = Math.max(0, hitStart - Math.floor(maxLen / 3))
  if (start > 0) {
    const space = text.lastIndexOf(' ', start)
    start = space === -1 ? start : space + 1
  }
  let end = Math.min(text.length, start + maxLen)
  if (end < text.length) {
    const space = text.lastIndexOf(' ', end)
    if (space > Math.max(start, hitEnd)) end = space
  }
  return `${start > 0 ? '…' : ''}${text.slice(start, end).trim()}${end < text.length ? '…' : ''}`
}

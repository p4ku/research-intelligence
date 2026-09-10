// Pure mappers from API DTOs to the domain types. No I/O, unit-tested.
//
// Parity notes: `sanitizeIdentifier` and `parseNumeric` mirror
// `_sanitize_identifier` / `_parse_numeric_value` in the backend's
// tasks/step_6_signal_score/scorer.py; `resolveExitMetric` mirrors tiers 2–3
// of `Extraction.exit_metric` in research_intelligence/models.py. Tier 1 needs
// the definition's exit key, which the API does not expose — but the
// extraction row serialises the resolved `exit_metric` itself, and
// `exitFromRow` reads the headline off that when it is there.

import type {
  ExtractionDTO,
  ExtractionDefinitionDTO,
  FieldExtractionDTO,
  PaperDTO,
  PaperMetricDTO,
  WorkspaceDTO,
} from '@/lib/api/types'
import type { ScoreVariableValue } from '@/lib/bff/papers/schema'
import { signalScoreOf, trlLevel } from './score'
import {
  PASSED_STATUSES,
  SCREENING_STATUSES,
  type DefinitionSummary,
  type Dimension,
  type ScoredPaper,
  type ScreeningStatus,
  type WorkspaceSummary,
} from './types'

/* ------------------------------ Primitive ports ----------------------------- */

/** 'TRL Level' → 'trl_level'; 'Fit-Score (0-100)' → 'fit_score_0_100'. */
export function sanitizeIdentifier(name: string | null | undefined): string {
  if (!name) return 'param'
  let clean = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]/g, '_')
  clean = clean.replace(/_+/g, '_').replace(/^_+|_+$/g, '')
  if (clean && /^\d/.test(clean)) clean = `v_${clean}`
  return clean || 'param'
}

const FIRST_NUMBER = /[-+]?\d*\.?\d+/

/** Numeric reading of a field value, or null. "85%" → 0.85, "TRL 4" → 4, "High" → null. */
export function parseNumeric(value: unknown): number | null {
  if (value === null || value === undefined) return null
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'boolean') return null
  if (typeof value === 'object') {
    const v = value as Record<string, unknown>
    if ('value' in v && v.value !== null && v.value !== undefined) return parseNumeric(v.value)
    if (
      'normalized_value' in v &&
      v.normalized_value !== null &&
      v.normalized_value !== undefined
    ) {
      return parseNumeric(v.normalized_value)
    }
    return null
  }
  const str = String(value).trim()
  if (!str || str === '-') return null
  if (str.endsWith('%')) {
    const pct = Number(str.slice(0, -1).trim())
    if (Number.isFinite(pct)) return pct / 100
  }
  const direct = Number(str)
  if (Number.isFinite(direct)) return direct
  const match = FIRST_NUMBER.exec(str)
  if (match) {
    const n = Number(match[0])
    if (Number.isFinite(n)) return n
  }
  return null
}

/** Unwrap `{ fields: {...} }` and drop non-object payloads. */
export function fieldsOf(fieldsData: ExtractionDTO['fields_data']): Record<string, unknown> {
  if (!fieldsData || typeof fieldsData !== 'object' || Array.isArray(fieldsData)) return {}
  const data = fieldsData as Record<string, unknown>
  const nested = data.fields
  if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
    return nested as Record<string, unknown>
  }
  return data
}

function keyNorm(k: string): string {
  return k.toLowerCase().replace(/ /g, '_')
}

function isFieldExtraction(v: unknown): v is FieldExtractionDTO {
  return Boolean(v) && typeof v === 'object' && !Array.isArray(v) && 'value' in (v as object)
}

function scalarToString(v: unknown): string | null {
  if (isFieldExtraction(v))
    return v.value === null || v.value === undefined ? null : String(v.value)
  if (v === null || v === undefined) return null
  if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') return String(v)
  return null
}

/**
 * The headline value of an extraction, as the backend's `exit_metric`
 * property would resolve it without a configured exit key.
 */
export function resolveExitMetric(
  fieldsData: ExtractionDTO['fields_data'],
  definitionName: string | null | undefined,
  category: string | null | undefined,
): { raw: string; matchedKey: string | null } {
  const data = fieldsOf(fieldsData)
  const entries = Object.entries(data)
  if (entries.length === 0) return { raw: '-', matchedKey: null }

  // Tier 2: candidate keys derived from the definition name and category.
  const candidates: string[] = []
  if (definitionName) {
    const n = keyNorm(definitionName)
    candidates.push(n, n.replace('_extraction', ''), n.replace('_score', ''))
  }
  if (category) {
    const c = keyNorm(category)
    candidates.push(c, c.replace('_extraction', ''))
  }
  for (const candidate of candidates) {
    for (const [k, v] of entries) {
      if (keyNorm(k) === candidate) {
        const s = scalarToString(v)
        if (s !== null) return { raw: s, matchedKey: k }
      }
    }
  }

  // Tier 3: first non-empty scalar (excluding long text / urls).
  for (const [k, v] of entries) {
    if (isFieldExtraction(v)) {
      const s = scalarToString(v)
      if (s !== null) return { raw: s, matchedKey: k }
    } else if (typeof v === 'number' || typeof v === 'boolean') {
      return { raw: String(v), matchedKey: k }
    } else if (typeof v === 'string' && v.length < 80 && !v.startsWith('http')) {
      return { raw: v, matchedKey: k }
    }
  }
  return { raw: '-', matchedKey: null }
}

const TRL_NAME = /\btrl\b/i
const RANGE_IN_TEXT = /(\d+)\s*(?:-|–|to)\s*(\d+)/

export function isTrlName(name: string): boolean {
  return TRL_NAME.test(name)
}

/** Scale for bars/radar: TRL → 9; a "(1-10)" hint in the definition; else from the corpus. */
export function inferScale(
  def: Pick<ExtractionDefinitionDTO, 'name' | 'system_prompt'>,
  corpusMax: number | null,
): number | null {
  if (isTrlName(def.name)) return 9
  const hint = RANGE_IN_TEXT.exec(`${def.name} ${def.system_prompt ?? ''}`)
  if (hint) {
    const upper = Number(hint[2])
    if (Number.isFinite(upper) && upper > 0) return upper
  }
  if (corpusMax === null) return null
  if (corpusMax <= 1) return 1
  if (corpusMax <= 10) return 10
  if (corpusMax <= 100) return 100
  return null
}

/* ------------------------------ Field details ------------------------------- */

const RATIONALE_KEY = /(reason|rationale|justif)/i
// The quoted evidence — not every key with "evidence" in it: `evidence_gaps`
// is a list of what is missing and `evidence_of_movement` is prose.
const EVIDENCE_KEY = /(quote|^evidence$|_evidence$)/i

function detailsFor(
  data: Record<string, unknown>,
  matchedKey: string | null,
): { rationale?: string; evidence?: string[]; confidence?: number | null; used: string[] } {
  const matched = matchedKey ? data[matchedKey] : undefined
  let rationale: string | undefined
  let evidence: string[] | undefined
  let confidence: number | undefined
  const used: string[] = []
  // The nested form keeps its reasons on the matched field; a flat sibling
  // (`justification`, `confidence`) still counts, and is still consumed.
  if (isFieldExtraction(matched)) {
    const quotes = (matched.evidence ?? [])
      .map((e) => e?.quote)
      .filter((q): q is string => typeof q === 'string' && q.trim() !== '')
    const reasons = (matched.evidence ?? [])
      .map((e) => e?.rationale)
      .filter((r): r is string => typeof r === 'string' && r.trim() !== '')
      .join(' ')
    rationale = reasons || undefined
    evidence = quotes.length ? quotes : undefined
    confidence = typeof matched.confidence === 'number' ? matched.confidence : undefined
  }
  for (const [k, raw] of Object.entries(data)) {
    if (k === matchedKey) continue
    const v = isFieldExtraction(raw) ? raw.value : raw
    if (RATIONALE_KEY.test(k) && typeof v === 'string' && v.trim()) {
      if (rationale === undefined) rationale = v
      used.push(k)
    } else if (EVIDENCE_KEY.test(k)) {
      if (Array.isArray(v)) {
        const quotes = v.filter((q): q is string => typeof q === 'string' && q.trim() !== '')
        if (quotes.length) {
          if (evidence === undefined) evidence = quotes
          used.push(k)
        }
      } else if (typeof v === 'string' && v.trim()) {
        if (evidence === undefined) evidence = [v]
        used.push(k)
      }
    } else if (/confidence/i.test(k) && typeof v === 'number') {
      if (confidence === undefined) confidence = v
      used.push(k)
    }
  }
  return { rationale, evidence, confidence, used }
}

/* ---------------------------- Definition detail ----------------------------- */

// The extractor's postprocessing writes the exit metric back under two extra
// names; neither is a field of the definition.
const DUPLICATE_KEY = /_(computed|postprocessed)$/i
const FACET_KEY = /_score$/i
const ASSESSMENT_KEY = /_assessment$/i
const BAND_KEY = /_(band|label)$/i
const LEVEL_KEY = /_level$/i
// A string with a sentence in it reads as prose under its own heading; one
// without ("OpenMPI", "High") is a fact. Length would flip the same key
// between the two from paper to paper; punctuation is what the model varies
// least.
const SENTENCE = /[.!?](\s|$)/
const WORDS: Record<string, string> = {
  ai: 'AI',
  api: 'API',
  cpu: 'CPU',
  gdpr: 'GDPR',
  gpu: 'GPU',
  hpc: 'HPC',
  iot: 'IoT',
  llm: 'LLM',
  lockin: 'lock-in',
  ml: 'ML',
  nlp: 'NLP',
  qpu: 'QPU',
  sla: 'SLA',
  stackit: 'STACKIT',
  trl: 'TRL',
}

/** `need_match_score` → "Need match"; `stackit_sovereignty_score` → "STACKIT sovereignty". */
export function humaniseKey(key: string): string {
  const words = key
    .replace(/_(score|assessment)$/i, '')
    .split('_')
    .filter(Boolean)
    .map((w) => WORDS[w.toLowerCase()] ?? w)
  const s = words.join(' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}

/** "TRL 4: Technology validated in lab" → "Technology validated in lab". */
function bandLabel(value: string): string {
  return value.replace(/^TRL\s*\d+\s*[:\-–]\s*/i, '').trim()
}

/**
 * Tier 1 of the backend's exit-metric resolution: the row's own `exit_metric`
 * is the headline value, and the definition's first exit key names the field
 * it came from. Without the key (an orphan, an older definition) the field
 * holding the value stands in — score and level keys first, numbers compared
 * as numbers — and failing that the name-derived key, so the headline field
 * is never filed as a facet of itself.
 */
function exitFromRow(
  extraction: Pick<ExtractionDTO, 'exit_metric'>,
  data: Record<string, unknown>,
  exitKey: string | undefined,
  fallbackKey: string | null,
): { raw: string; matchedKey: string | null } | null {
  const exit = extraction.exit_metric?.trim()
  if (!exit || exit === '-') return null
  if (exitKey && scalarToString(data[exitKey]) !== null) return { raw: exit, matchedKey: exitKey }
  const n = Number(exit)
  const entries = Object.entries(data).filter(([k]) => !DUPLICATE_KEY.test(k))
  const ordered = [
    ...entries.filter(([k]) => FACET_KEY.test(k) || LEVEL_KEY.test(k)),
    ...entries.filter(([k]) => !(FACET_KEY.test(k) || LEVEL_KEY.test(k))),
  ]
  for (const [k, v] of ordered) {
    const value = isFieldExtraction(v) ? v.value : v
    const hit =
      typeof value === 'number'
        ? Number.isFinite(n) && value === n
        : typeof value === 'string' && value.trim() === exit
    if (hit) return { raw: exit, matchedKey: k }
  }
  return { raw: exit, matchedKey: fallbackKey }
}

type DimensionDetail = Pick<Dimension, 'band' | 'facets' | 'texts' | 'lists' | 'facts'>

/**
 * Everything the definition emitted that the headline, rationale and
 * evidence did not consume, sorted by shape: `*_score` numbers are facets
 * (a `*_assessment` twin rides along as their text), `*_band` / `*_label`
 * strings are the band, arrays are lists, long strings are prose, and the
 * rest are facts. Payload order throughout, so the page reads in the order
 * the definition's schema was written.
 */
function dimensionDetail(
  data: Record<string, unknown>,
  used: Set<string>,
  headline: number | null,
  facetMax: number | null,
  /** The definition's exit keys after the headline: the admin's order for the facets. */
  order: readonly string[] = [],
): DimensionDetail {
  const facets: NonNullable<Dimension['facets']> = []
  const texts: NonNullable<Dimension['texts']> = []
  const lists: NonNullable<Dimension['lists']> = []
  const facts: NonNullable<Dimension['facts']> = []
  let band: string | undefined
  // 1. If explicit secondary metrics are specified in `order`, build facets directly
  if (order.length > 0) {
    for (const secKey of order) {
      if (used.has(secKey)) continue
      const raw =
        data[secKey] ??
        Object.entries(data).find(
          ([k]) =>
            k.toLowerCase().replace(/[-_ ]/g, '') === secKey.toLowerCase().replace(/[-_ ]/g, ''),
        )?.[1]
      if (raw === undefined) continue
      const value = isFieldExtraction(raw) ? raw.value : raw
      const name = humaniseKey(secKey)

      let dictValue: Record<string, unknown> | null = null
      if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
        dictValue = value as Record<string, unknown>
      } else if (
        typeof value === 'string' &&
        value.trim().startsWith('{') &&
        value.trim().endsWith('}')
      ) {
        try {
          const parsed = JSON.parse(value.trim())
          if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
            dictValue = parsed
          }
        } catch {
          // ignore
        }
      }

      if (dictValue) {
        const b = dictValue.band ? String(dictValue.band).trim() : null
        const insRaw =
          dictValue.insight ??
          dictValue.rationale ??
          dictValue.reasoning ??
          dictValue.explanation ??
          dictValue.text ??
          dictValue.summary
        const ins = insRaw !== undefined && insRaw !== null ? String(insRaw).trim() : null
        const evRaw = dictValue.evidence ?? dictValue.quotes ?? dictValue.snippets
        let ev: string[] | null = null
        if (Array.isArray(evRaw)) {
          ev = evRaw
            .map((e) =>
              typeof e === 'object' && e !== null && 'quote' in e
                ? String((e as { quote: unknown }).quote)
                : String(e),
            )
            .map((s) => s.trim())
            .filter(Boolean)
        }
        const sRaw = dictValue.score ?? dictValue.value
        const sc = typeof sRaw === 'number' && Number.isFinite(sRaw) ? sRaw : null

        if (sc !== null) {
          facets.push({
            key: secKey,
            name,
            value: sc,
            max: facetMax,
            text: ins,
            band: b,
          })
        } else {
          texts.push({
            key: secKey,
            name,
            value: ins || (b ? b : '—'),
            type: 'dict',
            is_dict: true,
            dict_value: dictValue,
            band: b,
            insight: ins,
            evidence: ev,
            score: sc,
          })
        }
        used.add(secKey)
        continue
      }

      if (typeof value === 'number' && Number.isFinite(value)) {
        const twin = data[secKey.replace(FACET_KEY, '_assessment')] ?? data[`${secKey}_assessment`]
        const text = isFieldExtraction(twin) ? twin.value : twin
        facets.push({
          key: secKey,
          name,
          value,
          max: facetMax,
          text: typeof text === 'string' && text.trim() ? text : null,
        })
        used.add(secKey)
        continue
      }

      if (typeof value === 'string') {
        facts.push({ key: secKey, name, value })
        used.add(secKey)
      }
    }
  }

  for (const [key, raw] of Object.entries(data)) {
    if (used.has(key) || DUPLICATE_KEY.test(key)) continue
    const value = isFieldExtraction(raw) ? raw.value : raw
    const name = humaniseKey(key)
    if (typeof value === 'string' && BAND_KEY.test(key)) {
      if (band === undefined && value.trim()) band = bandLabel(value)
      continue
    }
    // Only scan for _score facets if no secondary metrics order was specified (legacy fallback)
    if (
      order.length === 0 &&
      typeof value === 'number' &&
      Number.isFinite(value) &&
      FACET_KEY.test(key)
    ) {
      const twin = data[key.replace(FACET_KEY, '_assessment')]
      const text = isFieldExtraction(twin) ? twin.value : twin
      facets.push({
        key,
        name,
        value,
        max: facetMax,
        text: typeof text === 'string' && text.trim() ? text : null,
      })
      continue
    }
    if (typeof value === 'string' && ASSESSMENT_KEY.test(key)) {
      // Paired with its facet above; on its own it is prose like any other.
      if (key.replace(ASSESSMENT_KEY, '_score') in data) continue
    }
    // Dictionary / structured sub-metric (e.g. { band: 'Substantial', score: 68, insight: '...', evidence: [...] })
    let dictValue: Record<string, unknown> | null = null
    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      dictValue = value as Record<string, unknown>
    } else if (
      typeof value === 'string' &&
      value.trim().startsWith('{') &&
      value.trim().endsWith('}')
    ) {
      try {
        const parsed = JSON.parse(value.trim())
        if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
          dictValue = parsed
        }
      } catch {
        // ignore
      }
    }

    if (dictValue) {
      const b = dictValue.band ? String(dictValue.band).trim() : null
      const insRaw =
        dictValue.insight ??
        dictValue.rationale ??
        dictValue.reasoning ??
        dictValue.explanation ??
        dictValue.text ??
        dictValue.summary
      const ins = insRaw !== undefined && insRaw !== null ? String(insRaw).trim() : null
      const evRaw = dictValue.evidence ?? dictValue.quotes ?? dictValue.snippets
      let ev: string[] | null = null
      if (Array.isArray(evRaw)) {
        ev = evRaw
          .map((e) =>
            typeof e === 'object' && e !== null && 'quote' in e
              ? String((e as { quote: unknown }).quote)
              : String(e),
          )
          .map((s) => s.trim())
          .filter(Boolean)
      }
      const sRaw = dictValue.score ?? dictValue.value
      const sc = typeof sRaw === 'number' && Number.isFinite(sRaw) ? sRaw : null

      if (order.length === 0 && sc !== null && !facets.some((f) => f.key === key)) {
        facets.push({
          key,
          name,
          value: sc,
          max: facetMax,
          text: ins,
          band: b,
        })
      } else {
        texts.push({
          key,
          name,
          value: ins || (b ? b : '—'),
          type: 'dict',
          is_dict: true,
          dict_value: dictValue,
          band: b,
          insight: ins,
          evidence: ev,
          score: sc,
        })
      }
      continue
    }

    if (Array.isArray(value)) {
      const items = value.filter((i): i is string => typeof i === 'string' && i.trim() !== '')
      if (items.length) lists.push({ key, name, items })
      continue
    }
    if (typeof value === 'boolean') {
      facts.push({ key, name, value })
      continue
    }
    if (typeof value === 'string') {
      const s = value.trim()
      if (!s) continue
      if (SENTENCE.test(s)) texts.push({ key, name, value: s })
      else facts.push({ key, name, value: s })
      continue
    }
    if (typeof value === 'number' && Number.isFinite(value)) {
      // `trl_level` beside a `trl_label` headline is the same number twice.
      if (LEVEL_KEY.test(key) && value === headline) continue
      facts.push({ key, name, value: String(value) })
    }
  }
  const rank = (key: string) => {
    const i = order.indexOf(key)
    return i < 0 ? order.length : i
  }
  facets.sort((a, b) => rank(a.key) - rank(b.key))
  return {
    band,
    facets: facets.length ? facets : undefined,
    texts: texts.length ? texts : undefined,
    lists: lists.length ? lists : undefined,
    facts: facts.length ? facts : undefined,
  }
}

function modelOf(extraction: Pick<ExtractionDTO, 'version_info'>): string | null {
  const model = extraction.version_info?.llm_model
  return typeof model === 'string' && model.trim() ? model : null
}

/* --------------------------------- Metrics ---------------------------------- */

/** The PaperMetric for the paper's own run, else the newest. */
export function pickMetric(
  paper: Pick<PaperDTO, 'pipeline_run' | 'metrics'>,
): PaperMetricDTO | null {
  const metrics = paper.metrics ?? []
  if (metrics.length === 0) return null
  return (
    metrics.find((m) => m.pipeline_run === paper.pipeline_run) ??
    metrics.slice().sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''))[0]
  )
}

/* --------------------------------- Helpers ---------------------------------- */

export function splitAuthors(raw: string | null | undefined): string[] {
  if (!raw) return []
  return raw
    .split(/\s*,\s*|\s*;\s*|\s+and\s+/i)
    .map((a) => a.trim())
    .filter(Boolean)
}

/**
 * One line, single-spaced. Sources wrap long titles and abstracts across
 * lines — arXiv's Atom feed breaks a title as `…quantum-classical\n  computations`
 * — and that wrap is a transport artefact, not part of the text. HTML collapses
 * it when the string lands in a paragraph, but not in an input value, a tooltip,
 * a `document.title`, or anything we copy, search, or send to the model, so we
 * collapse it once here rather than at each of those.
 *
 * ASCII whitespace only, on purpose: a line wrap is never a no-break space,
 * and NBSP inside a title (`10 kg`, `Fig. 1`) is typography we must keep. It
 * also keeps this identical to the backend's `one_line` — `\s` differs between
 * the two engines on NEL and U+FEFF.
 *
 * The wrap can also arrive *escaped* — OpenAlex serves some works with the
 * backslash and the letter as two characters — and is collapsed only in a
 * field that is escape-encoded as a whole (ESCAPED_FIELD_MARK). TeX starts
 * the same way and abstracts carry it bare (`\nabla`, `\textbf{..}`), so
 * nothing local tells `of\nquantum` from `\nabla`; the mark does. This is
 * the read side of the backend's rule, cleaning the rows already stored.
 */
export function oneLine(raw: string | null | undefined): string {
  if (!raw) return ''
  const text = ESCAPED_FIELD_MARK.test(raw) ? raw.replace(ESCAPED_WRAP, ' ') : raw
  return text.replace(WHITESPACE, ' ').trim()
}

const WHITESPACE = /[ \t\r\n\f\v]+/g
// A line wrap that took a JSON round-trip upstream: backslash + n as two
// characters (CRLF included). A doubled backslash is TeX's own `\\`, left alone.
const ESCAPED_WRAP = /(?<!\\)(?:\\r)?\\n/g
// An escaped wrap right before whitespace or the end of the field. No TeX
// control word looks like that (`\nabla`, `\newline`, `\neq` all continue), so
// one of these marks the whole field as escape-encoded.
const ESCAPED_FIELD_MARK = /(?<!\\)(?:\\r)?\\n(?=\s|$)/

/* ---------------------------------- Links ---------------------------------- */

// New-style "2401.12345(v2)" or old-style "cond-mat/0102536", "cs.CV/0101001".
const ARXIV_ID = /^(\d{4}\.\d{4,5}|[a-z-]+(\.[a-z-]+)?\/\d{7})(v\d+)?$/i

/**
 * The arXiv id in `value` — an `arXiv:` prefix and whitespace stripped — or
 * null when it is not shaped like one. The backend's arXiv fallback can leave
 * an OpenAlex work id ("W2781738013") in `arxiv_id`, and its backfill turned
 * such rows into `https://arxiv.org/abs/W…`, so nothing is shown as arXiv
 * without passing through here.
 */
export function arxivId(value: string | null | undefined): string | null {
  const id = (value ?? '').trim().replace(/^arxiv:/i, '')
  return ARXIV_ID.test(id) ? id : null
}

/** `http(s)` links only — a provider string with any other scheme is not a link we render. */
export function httpUrl(value: string | null | undefined): string | null {
  return value && /^https?:\/\//i.test(value) ? value : null
}

/** The decoded path of an http(s) `url` on a host matching `host`, trailing slash off; else null. */
function pathOn(url: string | null | undefined, host: RegExp): string | null {
  if (!httpUrl(url)) return null
  try {
    const u = new URL(url as string)
    if (!host.test(u.hostname)) return null
    return decodeURIComponent(u.pathname).replace(/\/+$/, '')
  } catch {
    return null
  }
}

/** The arXiv id a `source_url` points at, or null — query and fragment aside, shape-checked. */
export function arxivIdOf(url: string | null | undefined): string | null {
  const path = pathOn(url, /^(www\.|export\.)?arxiv\.org$/i)
  return arxivId(/^\/abs\/(.+)$/.exec(path ?? '')?.[1])
}

/** The DOI a `source_url` points at, or null. */
export function doiOf(url: string | null | undefined): string | null {
  const doi = pathOn(url, /^(dx\.)?doi\.org$/i)?.slice(1)
  return doi || null
}

export function normalizeStatus(value: string | null | undefined): ScreeningStatus {
  return (SCREENING_STATUSES as string[]).includes(value ?? '')
    ? (value as ScreeningStatus)
    : 'pending'
}

export function isPassed(status: ScreeningStatus): boolean {
  return PASSED_STATUSES.includes(status)
}

/* -------------------------------- Composition ------------------------------- */

interface DefinitionContext {
  def: ExtractionDefinitionDTO
  key: string
  is_trl: boolean
  max: number | null
}

/** Per-definition corpus maximum from every extraction in the workspace. */
export function corpusMaxima(
  definitions: ExtractionDefinitionDTO[],
  extractions: ExtractionDTO[],
): Map<string, number | null> {
  const byDefId = new Map(definitions.map((d) => [d.id, d]))
  const byName = new Map(definitions.map((d) => [d.name, d]))
  const maxima = new Map<string, number | null>(definitions.map((d) => [d.id, null]))
  for (const ext of extractions) {
    const def =
      (ext.extraction_definition && byDefId.get(ext.extraction_definition)) ||
      byName.get(ext.category)
    if (!def) continue
    // The same headline the dimension will show, so the scale fits it.
    const raw =
      ext.exit_metric?.trim() || resolveExitMetric(ext.fields_data, def.name, ext.category).raw
    const n = parseNumeric(raw)
    if (n === null) continue
    const current = maxima.get(def.id) ?? null
    maxima.set(def.id, current === null ? n : Math.max(current, n))
  }
  return maxima
}

export function definitionContexts(
  definitions: ExtractionDefinitionDTO[],
  maxima: Map<string, number | null>,
): DefinitionContext[] {
  return definitions.map((def) => ({
    def,
    key: sanitizeIdentifier(def.name),
    is_trl: isTrlName(def.name),
    max: inferScale(def, maxima.get(def.id) ?? null),
  }))
}

function dimensionFor(
  ctx: DefinitionContext,
  extraction: ExtractionDTO | undefined,
  metric: PaperMetricDTO | null,
  detail: boolean,
): Dimension {
  const base: Dimension = {
    key: ctx.key,
    definition_id: ctx.def.id,
    name: ctx.def.name,
    value: null,
    raw: '—',
    max: ctx.max,
    is_trl: ctx.is_trl,
  }
  // No extraction row → no value, even though metrics_data pre-fills 0.0.
  if (!extraction) return base

  const data = fieldsOf(extraction.fields_data)
  const named = resolveExitMetric(extraction.fields_data, ctx.def.name, extraction.category)
  const explicitPrim = ctx.def.primary_frontend_metric ?? undefined
  const explicitSec = ctx.def.secondary_frontend_metrics
  const exitKeys = ctx.def.exit_metrics ?? []
  const targetPrim = explicitPrim || exitKeys[0]
  const targetSec = explicitSec !== undefined ? explicitSec : exitKeys.slice(1)
  const { raw, matchedKey } = exitFromRow(extraction, data, targetPrim, named.matchedKey) ?? named
  // metrics_data is pre-filled with 0.0 for every definition, so a bare 0
  // there is indistinguishable from "never scored" — only a non-zero metric
  // outranks the parsed extraction value ("null not 0", like parseNumeric).
  const fromMetric = metric?.metrics_data?.[ctx.key]
  let value = typeof fromMetric === 'number' && fromMetric !== 0 ? fromMetric : parseNumeric(raw)
  if (ctx.is_trl && value !== null) value = trlLevel(value)

  const details = detailsFor(data, matchedKey)
  const used = new Set([...(matchedKey ? [matchedKey] : []), ...details.used])
  return {
    ...base,
    value,
    raw,
    rationale: details.rationale,
    evidence: details.evidence,
    confidence: details.confidence ?? extraction.confidence_score ?? null,
    validation_status: extraction.validation_status,
    review_required: extraction.review_required,
    extraction_id: extraction.id,
    // A TRL definition's sub-scores declare no range; the others share the
    // definition's own scale.
    ...(detail && {
      ...dimensionDetail(data, used, value, ctx.is_trl ? null : ctx.max, targetSec),
      model: modelOf(extraction),
      primary_frontend_metric: explicitPrim ?? null,
      secondary_frontend_metrics: targetSec,
    }),
  }
}

/** Extractions whose definition was deleted and matches no current name — detail page only. */
function orphanDimension(extraction: ExtractionDTO, detail: boolean): Dimension {
  const data = fieldsOf(extraction.fields_data)
  const named = resolveExitMetric(extraction.fields_data, null, extraction.category)
  const { raw, matchedKey } = exitFromRow(extraction, data, undefined, named.matchedKey) ?? named
  const details = detailsFor(data, matchedKey)
  const used = new Set([...(matchedKey ? [matchedKey] : []), ...details.used])
  const name = extraction.category || 'Extraction'
  const is_trl = isTrlName(name)
  const parsed = parseNumeric(raw)
  // An orphan named TRL is still a TRL: a whole 1–9 level, like the ones a
  // definition backs.
  const value = is_trl && parsed !== null ? trlLevel(parsed) : parsed
  return {
    key: sanitizeIdentifier(name),
    definition_id: null,
    name,
    value,
    raw,
    max: null,
    is_trl,
    rationale: details.rationale,
    evidence: details.evidence,
    confidence: details.confidence ?? extraction.confidence_score ?? null,
    validation_status: extraction.validation_status,
    review_required: extraction.review_required,
    extraction_id: extraction.id,
    ...(detail && { ...dimensionDetail(data, used, value, null), model: modelOf(extraction) }),
  }
}

function legacyTrlDimension(metric: PaperMetricDTO | null): Dimension | null {
  const data = metric?.metrics_data
  if (!data || typeof data.trl_score !== 'number') return null
  const reasoning = typeof data.trl_reasoning === 'string' ? data.trl_reasoning : undefined
  const evidence = Array.isArray(data.trl_evidence)
    ? (data.trl_evidence as unknown[]).filter((e): e is string => typeof e === 'string')
    : undefined
  const level = trlLevel(data.trl_score)
  return {
    key: 'trl_score',
    definition_id: null,
    name: 'TRL',
    value: level,
    // The reader is shown the level, not the unrounded figure behind it.
    raw: String(level),
    max: 9,
    is_trl: true,
    rationale: reasoning,
    evidence,
  }
}

/**
 * `detail` shapes the rest of each definition's payload (facets, prose,
 * lists, facts, model) — the paper page reads it; the list and run
 * compositions, which score the whole corpus, leave it out so a briefing or
 * the papers list never carries seven definitions' prose per paper.
 */
export function toScoredPaper(
  paper: PaperDTO,
  extractions: ExtractionDTO[],
  contexts: DefinitionContext[],
  { detail = true }: { detail?: boolean } = {},
): ScoredPaper {
  const metric = pickMetric(paper)
  const byDefId = new Map<string, ExtractionDTO>()
  const byCategory = new Map<string, ExtractionDTO>()
  const orphans: ExtractionDTO[] = []
  for (const ext of extractions) {
    if (ext.extraction_definition) {
      if (!byDefId.has(ext.extraction_definition)) byDefId.set(ext.extraction_definition, ext)
    } else if (ext.category && !byCategory.has(ext.category)) {
      byCategory.set(ext.category, ext)
    }
  }
  const dimensions: Dimension[] = []
  for (const ctx of contexts) {
    const ext = byDefId.get(ctx.def.id) ?? byCategory.get(ctx.def.name)
    if (ext) byCategory.delete(ctx.def.name)
    // Inactive definitions only show when this paper actually has a value.
    if (!ctx.def.is_active && !ext) continue
    dimensions.push(dimensionFor(ctx, ext, metric, detail))
  }
  for (const ext of extractions) {
    if (
      ext.extraction_definition &&
      !contexts.some((c) => c.def.id === ext.extraction_definition)
    ) {
      orphans.push(ext)
    }
  }
  for (const ext of [...byCategory.values(), ...orphans]) {
    dimensions.push(orphanDimension(ext, detail))
  }
  if (!dimensions.some((d) => d.is_trl)) {
    const legacy = legacyTrlDimension(metric)
    if (legacy) dimensions.push(legacy)
  }

  const details = metric?.signal_score_details
  const hasDetails = Boolean(details && typeof details === 'object' && Object.keys(details).length)
  // Read out first: the error is what tells a real 0 from the 0.0 the scorer
  // writes when the formula failed, so the score below needs it.
  const scoreError = hasDetails ? ((details as { error?: string | null }).error ?? null) : null

  return {
    id: paper.id,
    workspace_id: paper.workspace,
    pipeline_run_id: paper.pipeline_run ?? '',
    title: oneLine(paper.title),
    authors: splitAuthors(paper.authors),
    authors_raw: paper.authors ?? '',
    abstract: oneLine(paper.abstract),
    doi: paper.doi || null,
    arxiv_id: paper.arxiv_id || null,
    source: paper.source_database || '',
    screening_status: normalizeStatus(paper.screening_status),
    screening_reasoning: paper.screening_reasoning || null,
    abstract_screening_reasoning: paper.abstract_screening_reasoning || null,
    full_text_screening_reasoning: paper.full_text_screening_reasoning || null,
    signal_score: signalScoreOf(metric?.signal_score, { error: scoreError }),
    signal_score_details: hasDetails
      ? {
          variables:
            (details as { variables?: Record<string, ScoreVariableValue> }).variables ?? {},
          code_snippet: (details as { code_snippet?: string }).code_snippet ?? null,
          calculated_at: (details as { calculated_at?: string }).calculated_at ?? null,
          error: scoreError,
        }
      : null,
    dimensions,
    pdf_key: paper.original_pdf_path || null,
    markdown_key: paper.converted_md_path || null,
    // The backend's one link rule, passed through — never rebuilt from the ids.
    // Only the scheme is checked: scraper output goes straight into an href.
    source_url: httpUrl(paper.source_url),
    is_benchmark: Boolean(paper.is_evaluation_benchmark),
    evaluation_label: paper.evaluation_label ?? null,
    published_date: paper.published_date || null,
    created_at: paper.created_at,
    pipeline_run_name: paper.pipeline_run_name || null,
  }
}

export function toWorkspaceSummary(
  ws: WorkspaceDTO,
  maxima: Map<string, number | null>,
): WorkspaceSummary {
  return {
    id: ws.id,
    name: ws.name,
    user_role: ws.user_role ?? null,
    scrapers: ws.scrapers.map((s) => ({
      id: s.id,
      provider: s.provider,
      search_query: s.search_query,
      is_active: s.is_active,
    })),
    digest_schedule: ws.digest_schedule || null,
    screening_llm_model: ws.screening_llm_model || null,
    llm_provider: ws.llm_provider || null,
    created_at: ws.created_at,
    definitions: ws.extraction_definitions.map(
      (d): DefinitionSummary => ({
        id: d.id,
        name: d.name,
        key: sanitizeIdentifier(d.name),
        is_active: d.is_active,
        is_trl: isTrlName(d.name),
        max: inferScale(d, maxima.get(d.id) ?? null),
        primary_frontend_metric: d.primary_frontend_metric ?? null,
        secondary_frontend_metrics: d.secondary_frontend_metrics ?? [],
      }),
    ),
  }
}

// Pure mappers from API DTOs to the domain types. No I/O, unit-tested.
//
// Parity notes: `sanitizeIdentifier` and `parseNumeric` mirror
// `_sanitize_identifier` / `_parse_numeric_value` in the backend's
// tasks/step_6_signal_score/scorer.py; `resolveExitMetric` mirrors tiers 2–3
// of `Extraction.exit_metric` in research_intelligence/models.py (tier 1 needs
// the definition's exit key, which the API does not expose).

import type {
  ExtractionDTO,
  ExtractionDefinitionDTO,
  FieldExtractionDTO,
  PaperDTO,
  PaperMetricDTO,
  WorkspaceDTO,
} from '@/lib/api/types'
import type { ScoreVariableValue } from '@/lib/bff/papers/schema'
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
const EVIDENCE_KEY = /(evidence|quote)/i

function detailsFor(
  data: Record<string, unknown>,
  matchedKey: string | null,
): { rationale?: string; evidence?: string[]; confidence?: number | null } {
  const matched = matchedKey ? data[matchedKey] : undefined
  if (isFieldExtraction(matched)) {
    const evidence = (matched.evidence ?? [])
      .map((e) => e?.quote)
      .filter((q): q is string => typeof q === 'string' && q.trim() !== '')
    const rationale = (matched.evidence ?? [])
      .map((e) => e?.rationale)
      .filter((r): r is string => typeof r === 'string' && r.trim() !== '')
      .join(' ')
    return {
      rationale: rationale || undefined,
      evidence: evidence.length ? evidence : undefined,
      confidence: typeof matched.confidence === 'number' ? matched.confidence : undefined,
    }
  }
  let rationale: string | undefined
  let evidence: string[] | undefined
  let confidence: number | undefined
  for (const [k, v] of Object.entries(data)) {
    if (k === matchedKey) continue
    if (rationale === undefined && RATIONALE_KEY.test(k) && typeof v === 'string' && v.trim()) {
      rationale = v
    } else if (evidence === undefined && EVIDENCE_KEY.test(k)) {
      if (Array.isArray(v)) {
        const quotes = v.filter((q): q is string => typeof q === 'string' && q.trim() !== '')
        if (quotes.length) evidence = quotes
      } else if (typeof v === 'string' && v.trim()) {
        evidence = [v]
      }
    } else if (confidence === undefined && /confidence/i.test(k) && typeof v === 'number') {
      confidence = v
    }
  }
  return { rationale, evidence, confidence }
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
 */
export function oneLine(raw: string | null | undefined): string {
  if (!raw) return ''
  return raw.replace(/[ \t\r\n\f\v]+/g, ' ').trim()
}

export function externalPdfUrl(arxiv_id: string | null, doi: string | null): string | null {
  if (arxiv_id) return `https://arxiv.org/pdf/${arxiv_id.replace(/^arxiv:/i, '')}.pdf`
  if (doi) return `https://doi.org/${doi}`
  return null
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
    const { raw } = resolveExitMetric(ext.fields_data, def.name, ext.category)
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

  const { raw, matchedKey } = resolveExitMetric(
    extraction.fields_data,
    ctx.def.name,
    extraction.category,
  )
  // metrics_data is pre-filled with 0.0 for every definition, so a bare 0
  // there is indistinguishable from "never scored" — only a non-zero metric
  // outranks the parsed extraction value ("null not 0", like parseNumeric).
  const fromMetric = metric?.metrics_data?.[ctx.key]
  let value = typeof fromMetric === 'number' && fromMetric !== 0 ? fromMetric : parseNumeric(raw)
  if (ctx.is_trl && value !== null) value = Math.min(9, Math.max(1, Math.round(value)))

  const details = detailsFor(fieldsOf(extraction.fields_data), matchedKey)
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
  }
}

/** Extractions whose definition was deleted and matches no current name — detail page only. */
function orphanDimension(extraction: ExtractionDTO): Dimension {
  const { raw, matchedKey } = resolveExitMetric(extraction.fields_data, null, extraction.category)
  const details = detailsFor(fieldsOf(extraction.fields_data), matchedKey)
  const name = extraction.category || 'Extraction'
  return {
    key: sanitizeIdentifier(name),
    definition_id: null,
    name,
    value: parseNumeric(raw),
    raw,
    max: null,
    is_trl: isTrlName(name),
    rationale: details.rationale,
    evidence: details.evidence,
    confidence: details.confidence ?? extraction.confidence_score ?? null,
    validation_status: extraction.validation_status,
    review_required: extraction.review_required,
    extraction_id: extraction.id,
  }
}

function legacyTrlDimension(metric: PaperMetricDTO | null): Dimension | null {
  const data = metric?.metrics_data
  if (!data || typeof data.trl_score !== 'number') return null
  const reasoning = typeof data.trl_reasoning === 'string' ? data.trl_reasoning : undefined
  const evidence = Array.isArray(data.trl_evidence)
    ? (data.trl_evidence as unknown[]).filter((e): e is string => typeof e === 'string')
    : undefined
  return {
    key: 'trl_score',
    definition_id: null,
    name: 'TRL',
    value: Math.min(9, Math.max(1, Math.round(data.trl_score))),
    raw: String(data.trl_score),
    max: 9,
    is_trl: true,
    rationale: reasoning,
    evidence,
  }
}

export function toScoredPaper(
  paper: PaperDTO,
  extractions: ExtractionDTO[],
  contexts: DefinitionContext[],
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
    dimensions.push(dimensionFor(ctx, ext, metric))
  }
  for (const ext of extractions) {
    if (
      ext.extraction_definition &&
      !contexts.some((c) => c.def.id === ext.extraction_definition)
    ) {
      orphans.push(ext)
    }
  }
  for (const ext of [...byCategory.values(), ...orphans]) dimensions.push(orphanDimension(ext))
  if (!dimensions.some((d) => d.is_trl)) {
    const legacy = legacyTrlDimension(metric)
    if (legacy) dimensions.push(legacy)
  }

  const details = metric?.signal_score_details
  const hasDetails = Boolean(details && typeof details === 'object' && Object.keys(details).length)

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
    signal_score: typeof metric?.signal_score === 'number' ? metric.signal_score : null,
    signal_score_details: hasDetails
      ? {
          variables:
            (details as { variables?: Record<string, ScoreVariableValue> }).variables ?? {},
          code_snippet: (details as { code_snippet?: string }).code_snippet ?? null,
          calculated_at: (details as { calculated_at?: string }).calculated_at ?? null,
          error: (details as { error?: string | null }).error ?? null,
        }
      : null,
    dimensions,
    pdf_key: paper.original_pdf_path || null,
    markdown_key: paper.converted_md_path || null,
    pdf_url: externalPdfUrl(paper.arxiv_id, paper.doi),
    is_benchmark: Boolean(paper.is_evaluation_benchmark),
    evaluation_label: paper.evaluation_label ?? null,
    created_at: paper.created_at,
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
      }),
    ),
  }
}

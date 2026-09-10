/**
 * Resolving `ComponentRun.metrics` — free-form engine JSON — into the typed
 * `summary` and `cost` the contract promises. Pure: no I/O, no server-only
 * imports, so `service.test.ts` can run it over a production snapshot.
 *
 * Two rules this module exists to hold:
 *  - absent is not zero (`{kind:'none'}`, `cost.usd === null`);
 *  - never estimate. Only what the engine measured is reported.
 */
import { clampScore } from '@/lib/papers/score'
import type { ComponentCost, ComponentSummary, StepType } from './schema'

/* ------------------------------ JSON readers ------------------------------ */

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

/** First key that holds a finite number, else null. Ignores 0-vs-absent games. */
function num(source: Record<string, unknown>, ...keys: string[]): number | null {
  for (const key of keys) {
    const value = source[key]
    if (typeof value === 'number' && Number.isFinite(value)) return value
    // DRF serialises Decimal as a string; engine metrics occasionally follow.
    if (typeof value === 'string' && value.trim() !== '') {
      const parsed = Number(value)
      if (Number.isFinite(parsed)) return parsed
    }
  }
  return null
}

/** A score-like number held to the 0–100 scale; null passes through. */
const capped = (value: number | null): number | null => (value === null ? null : clampScore(value))

function int(source: Record<string, unknown>, ...keys: string[]): number {
  const value = num(source, ...keys)
  return value === null ? 0 : Math.trunc(value)
}

/** True when at least one of the keys is present at all (even as 0/null). */
function has(source: Record<string, unknown>, ...keys: string[]): boolean {
  return keys.some((key) => key in source)
}

/* ------------------------------ Normalisation ----------------------------- */

/**
 * Step titles are frontend copy, not backend content: the engine sends a
 * `step_type`/`component_name` enum and this table names it in English. The
 * UI renders `t(step.label)`, so every value here needs a dictionary key —
 * guarded by `runs/run-presentation.test.ts` because the call is dynamic.
 */
export const STEP_LABELS: Record<StepType, string> = {
  search: 'Search',
  download: 'Download',
  ocr: 'OCR',
  screening: 'Screening',
  extraction: 'Extraction',
  signal_score: 'Signal score',
  metrics: 'Metrics',
  deep_research: 'Deep research',
  reporting: 'Reporting',
  unknown: 'Unrecognised step',
}

/** `component_name` is more specific than `step_type` where the engine splits a step. */
export const COMPONENT_LABELS: Record<string, string> = {
  abstract_screening: 'Abstract screening',
  full_text_screening: 'Full-text screening',
  arxiv_scraper: 'arXiv search',
  openalex_scraper: 'OpenAlex search',
  lens_scraper: 'Lens search',
  pubmed_scraper: 'PubMed search',
  document_download: 'Download',
  layout_ocr: 'Layout OCR',
  parameter_extraction: 'Parameter extraction',
  signal_score_evaluation: 'Signal score',
  executive_narrative: 'Executive narrative',
}

export function labelFor(step: StepType, componentName: string): string {
  return COMPONENT_LABELS[componentName] ?? STEP_LABELS[step]
}

/**
 * Resolve `metrics` (falling back to `output_data`, which some steps write
 * instead) into the per-step summary. Returns `{kind:'none'}` when the step
 * recorded nothing we can read, so the UI can say "no metrics recorded"
 * rather than render a fabricated zero.
 */
export function toSummary(step: StepType, metrics: unknown, outputData: unknown): ComponentSummary {
  const m = asRecord(metrics)
  const o = asRecord(outputData)
  const both = { ...o, ...m }

  switch (step) {
    case 'search': {
      if (!has(both, 'ingested_new', 'total_created', 'total_fetched', 'total_found')) break
      return {
        kind: 'search',
        created: int(both, 'ingested_new', 'total_created'),
        fetched: int(both, 'total_fetched', 'total_found'),
        duplicates: int(
          both,
          'duplicates_count',
          'duplicates',
          'total_duplicates',
          'duplicates_skipped',
          'total_duplicates_skipped',
        ),
      }
    }
    case 'download': {
      if (!has(both, 'downloaded', 'cached', 'from_cache', 'failed')) break
      return {
        kind: 'download',
        downloaded: int(both, 'downloaded'),
        cached: int(both, 'cached', 'from_cache', 'cached_hits'),
        failed: int(both, 'failed'),
      }
    }
    case 'ocr': {
      // Real runs skip OCR entirely and write only `{status:'skipped'}`; the
      // status badge already says so, so claim nothing here.
      if (!has(both, 'ocr_converted', 'converted', 'failed')) break
      return {
        kind: 'ocr',
        converted: int(both, 'ocr_converted', 'converted'),
        failed: int(both, 'failed'),
      }
    }
    case 'screening': {
      if (!has(both, 'total_screened', 'passed', 'rejected')) break
      return {
        kind: 'screening',
        screened: int(both, 'total_screened'),
        passed: int(both, 'passed'),
        rejected: int(both, 'rejected'),
        withdrawn: int(both, 'withdrawn'),
      }
    }
    case 'extraction': {
      if (!has(both, 'extractions_created', 'completed_extractions', 'total_papers')) break
      return {
        kind: 'extraction',
        created: int(both, 'extractions_created', 'completed_extractions'),
        papers: int(both, 'total_papers'),
        definitions: int(both, 'total_definitions'),
        failed: int(both, 'failed'),
      }
    }
    case 'signal_score': {
      if (!has(both, 'scored_count', 'papers_scored', 'total_papers')) break
      return {
        kind: 'signal_score',
        scored: int(both, 'scored_count', 'papers_scored'),
        total: int(both, 'total_papers'),
        // The engine records these unrounded and uncapped; the step summary
        // reads on the same 0–100 scale as every other score.
        avg: capped(num(both, 'avg_signal_score')),
        max: capped(num(both, 'max_signal_score', 'top_score')),
      }
    }
    case 'reporting': {
      if (!has(both, 'report_generated', 'report_id', 'reports_generated')) break
      return {
        kind: 'reporting',
        generated:
          both.report_generated === true ||
          typeof both.report_id === 'string' ||
          int(both, 'reports_generated') > 0,
        characters: num(both, 'characters_count') === null ? null : int(both, 'characters_count'),
      }
    }
    default:
      break
  }
  return { kind: 'none' }
}

/** Measured spend only — absent stays null rather than becoming $0.0000. */
export function toCost(metrics: unknown, outputData: unknown): ComponentCost {
  const both = { ...asRecord(outputData), ...asRecord(metrics) }
  const tokensIn = num(both, 'tokens_in', 'input_tokens', 'prompt_tokens')
  const tokensOut = num(both, 'tokens_out', 'output_tokens', 'candidates_tokens')
  const total = num(both, 'total_tokens', 'total_tokens_consumed')
  const model = both.model_used ?? both.model
  return {
    usd: num(both, 'usd_cost'),
    tokens_in: tokensIn === null ? null : Math.trunc(tokensIn),
    tokens_out: tokensOut === null ? null : Math.trunc(tokensOut),
    total_tokens:
      total !== null
        ? Math.trunc(total)
        : tokensIn !== null && tokensOut !== null
          ? Math.trunc(tokensIn + tokensOut)
          : null,
    model: typeof model === 'string' && model.trim() !== '' ? model : null,
  }
}

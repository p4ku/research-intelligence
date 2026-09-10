/**
 * A briefing's papers cut down to what its cards and rail read. The list is
 * a client component, so every row crosses the wire in the RSC payload; a
 * row as the run's scorecard fills it in weighs ~21 KB (measured on prod,
 * 9 Sep 2026: four dimensions at ~4 KB each, most of it `response_schema`),
 * which for the 566-paper briefing of 7 Sep 2026 is ~12 MB before a card
 * can paint. Trimmed, a row is under 2 KB.
 *
 * The shape stays `ScoredPaper` — the card and view.ts are typed against
 * it — with the fields no card shows nulled and the abstract cut. The card
 * clamps the abstract to two lines, so nothing past the cut is ever visible;
 * the paper page fetches its own record and is untouched by this.
 */
import type { Dimension, ScoredPaper } from '@/lib/papers/types'

/**
 * Characters of abstract kept. Two clamped lines hold ~200 characters at the
 * card's widest (85 a line at 1280 px), so the cut never shows; a mid-word
 * cut is hidden by the clamp's own ellipsis.
 */
export const ABSTRACT_CHARS = 400

/**
 * A dimension the card or the rail can use: one with a value. An unscored
 * one draws no stat and no TRL chip, is offered as no sort (sortOptions
 * skips it), and orders like a missing one (dimensionByKey → null) — the
 * run of 7 Sep 2026 carried four such per paper, a kilobyte of nothing.
 */
function usable(d: Dimension): boolean {
  return typeof d.value === 'number' && Number.isFinite(d.value)
}

/** The dimension as the card's stats, the TRL chip and the rail's sorts read it. */
function cardDimension(d: Dimension): Dimension {
  return {
    key: d.key,
    definition_id: d.definition_id,
    name: d.name,
    ...(d.label !== undefined && { label: d.label }),
    value: d.value,
    ...(d.raw !== undefined && { raw: d.raw }),
    max: d.max,
    is_trl: d.is_trl,
    ...(d.order !== undefined && { order: d.order }),
    ...(d.is_risk_and_affiliation !== undefined && {
      is_risk_and_affiliation: d.is_risk_and_affiliation,
    }),
  }
}

export function cardRow(p: ScoredPaper): ScoredPaper {
  // Edition rows are cast from `editionPaper`, whose abstract is optional
  // with no default — never dereference it bare.
  const abstract = p.abstract ?? ''
  return {
    ...p,
    abstract: abstract.length > ABSTRACT_CHARS ? abstract.slice(0, ABSTRACT_CHARS) : abstract,
    authors_raw: '',
    dimensions: (p.dimensions ?? []).filter(usable).map(cardDimension),
    screening_reasoning: null,
    abstract_screening_reasoning: null,
    full_text_screening_reasoning: null,
    signal_score_details: null,
    pdf_key: null,
    markdown_key: null,
    risk_and_affiliation: null,
    summary: null,
  }
}

export function cardRows(papers: readonly ScoredPaper[]): ScoredPaper[] {
  return papers.map(cardRow)
}

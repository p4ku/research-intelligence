/**
 * Which papers a run recorded, and what it recorded about them.
 *
 * Django keeps one PaperMetric per (paper, run), but its paper serializer
 * collapses a paper to a single run: the workspace's newest run where the
 * paper has a metric, else the paper's newest metric. Filtering the corpus
 * by `pipeline_run_id` therefore hands a paper to the latest run that saw it
 * and leaves every older briefing in the domain empty — a run whose counters
 * say 25 passed with nothing to list. An edition reads each run's own metric
 * row instead, through the index below. Pure, unit-tested.
 */
import type { PaperDTO } from '@/lib/api/types'
import { normalizeStatus } from './map'
import { signalScoreOf } from './score'
import type { ScoredPaper, ScreeningStatus } from './types'

/** One run's row for one paper. */
export interface RunRecord {
  /** null when the deployment's metric serializer omits it (see upstream.ts). */
  screening_status: ScreeningStatus | null
  /** The run's combined note: the full-text stage's, else the abstract stage's. */
  screening_reasoning: string | null
  /** The two stages apart, when the run kept them so — the paper page shows them as paragraphs. */
  abstract_screening_reasoning: string | null
  full_text_screening_reasoning: string | null
  signal_score: number | null
}

/** Run id → paper id → that run's record. */
export type RunIndex = Map<string, Map<string, RunRecord>>

export function indexRuns(papers: Pick<PaperDTO, 'id' | 'metrics'>[]): RunIndex {
  const index: RunIndex = new Map()
  // One row per (run, paper) is the model's rule; should two ever arrive
  // (the serializer substitutes the latest run for a null one), the newest
  // wins rather than whichever came last.
  const stamps = new Map<string, string>()
  for (const paper of papers) {
    for (const m of paper.metrics ?? []) {
      if (!m.pipeline_run) continue
      let ofRun = index.get(m.pipeline_run)
      if (!ofRun) index.set(m.pipeline_run, (ofRun = new Map()))
      const key = `${m.pipeline_run}/${paper.id}`
      const held = stamps.get(key)
      if (held !== undefined && held > m.created_at) continue
      stamps.set(key, m.created_at)
      ofRun.set(paper.id, {
        screening_status:
          typeof m.screening_status === 'string' ? normalizeStatus(m.screening_status) : null,
        screening_reasoning:
          m.full_text_screening_reasoning || m.abstract_screening_reasoning || null,
        abstract_screening_reasoning: m.abstract_screening_reasoning || null,
        full_text_screening_reasoning: m.full_text_screening_reasoning || null,
        signal_score: signalScoreOf(m.signal_score, m.signal_score_details),
      })
    }
  }
  return index
}

/** A paper as one run saw it: the run's decision and score over the paper's current record. */
export interface RunPaper {
  paper: ScoredPaper
  status: ScreeningStatus
  signal_score: number | null
  reason: string | null
}

/**
 * The papers a run recorded, as that run recorded them. Without an index
 * (papers not composed from Django's lists) the corpus's own attribution is
 * all there is. A row with no decision (the serializer lag above) takes the
 * paper's current one; a row with no reasoning takes the paper's only when
 * the paper itself reports this run — never a later run's words in this
 * run's log. The score is the run's own, null if that run never scored it.
 */
export function papersOfRun(
  runId: string,
  corpus: ReadonlyMap<string, ScoredPaper>,
  index: RunIndex | null,
): RunPaper[] {
  if (!index) {
    const out: RunPaper[] = []
    for (const paper of corpus.values()) {
      if (paper.pipeline_run_id !== runId) continue
      out.push({
        paper,
        status: paper.screening_status,
        signal_score: paper.signal_score,
        reason: paper.screening_reasoning,
      })
    }
    return out
  }
  const out: RunPaper[] = []
  for (const [id, record] of index.get(runId) ?? []) {
    const paper = corpus.get(id)
    if (!paper) continue
    out.push({
      paper,
      status: record.screening_status ?? paper.screening_status,
      signal_score: record.signal_score,
      reason:
        record.screening_reasoning ??
        (paper.pipeline_run_id === runId ? paper.screening_reasoning : null),
    })
  }
  return out
}

/** What an edition lists for a paper: the run's decision (when the source serves it) and score. */
export interface EditionEntry {
  screening_status?: ScreeningStatus | null
  signal_score: number | null
}

/**
 * One paper as one run recorded it, over its current record — the paper
 * page's view when opened from that run's briefing. The corpus's own record
 * when it already reports this run; else the run's index row (decision,
 * score, the stage reasons, and the run as provenance); else, past the
 * corpus cap where the index has no row, the edition's entry for status and
 * score with the reasons withheld — never a later run's words under this
 * run's decision. Null when the run never recorded the paper: the page then
 * shows the paper as it stands, as if no run were named.
 */
export function paperAsRun(
  paper: ScoredPaper,
  runId: string,
  index: RunIndex | null,
  entry: EditionEntry | null | undefined,
): ScoredPaper | null {
  if (paper.pipeline_run_id === runId) return paper
  const record = index?.get(runId)?.get(paper.id)
  if (record) {
    const [seen] = papersOfRun(runId, new Map([[paper.id, paper]]), index)
    return {
      ...paper,
      pipeline_run_id: runId,
      // The paper's run name is the latest run's; the ledger carries none.
      pipeline_run_name: null,
      screening_status: seen?.status ?? paper.screening_status,
      signal_score: record.signal_score,
      screening_reasoning: seen?.reason ?? null,
      abstract_screening_reasoning: record.abstract_screening_reasoning,
      full_text_screening_reasoning: record.full_text_screening_reasoning,
    }
  }
  if (!entry) return null
  return {
    ...paper,
    pipeline_run_id: runId,
    pipeline_run_name: null,
    screening_status: entry.screening_status ?? paper.screening_status,
    signal_score: entry.signal_score,
    screening_reasoning: null,
    abstract_screening_reasoning: null,
    full_text_screening_reasoning: null,
  }
}

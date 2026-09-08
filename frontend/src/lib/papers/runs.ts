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
import type { ScoredPaper, ScreeningStatus } from './types'

/** One run's row for one paper. */
export interface RunRecord {
  /** null when the deployment's metric serializer omits it (see upstream.ts). */
  screening_status: ScreeningStatus | null
  screening_reasoning: string | null
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
        signal_score: typeof m.signal_score === 'number' ? m.signal_score : null,
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
 * paper's current one; its reasoning and score are the run's own — null when
 * that run wrote none, never a later run's words in this run's log.
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
      reason: record.screening_reasoning,
    })
  }
  return out
}

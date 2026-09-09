/**
 * How the `composed` source turns runs and a scored corpus into editions —
 * the pure half of ../briefings/service.ts, so bun can test it without the
 * I/O. One edition per completed run that passed something, its papers as
 * that run recorded them (src/lib/papers/runs.ts), newest by completion
 * first. The service supplies the runs, the corpus and the run index.
 */
import type { Lang } from '@/lib/i18n'
import { isPassed } from '@/lib/papers/map'
import { papersOfRun, type RunIndex } from '@/lib/papers/runs'
import { byValueDesc } from '@/lib/papers/select'
import type { ScoredPaper } from '@/lib/papers/types'
import type { PipelineRun } from '../pipeline-runs/schema'
import { templateProse } from './prose'
import type { Edition } from './schema'
import { byNewest, editionDate } from './select'

export function composeEdition(
  run: PipelineRun,
  workspaceName: string,
  corpus: ReadonlyMap<string, ScoredPaper>,
  index: RunIndex | null,
  lang: Lang,
): Edition {
  // The run's own record of each paper — its decision and score then — not
  // the paper's latest, which belongs to whichever run saw it last.
  const ofRun = papersOfRun(run.id, corpus, index)
  const surfaced = ofRun
    .filter((r) => isPassed(r.status))
    .sort((a, b) => byValueDesc(a.signal_score, b.signal_score))
    .map(({ paper, status, signal_score }) => ({
      id: paper.id,
      title: paper.title,
      authors: paper.authors,
      source: paper.source,
      screening_status: status,
      signal_score,
    }))
  const exclusions = ofRun
    .filter((r) => r.status === 'rejected' || r.status === 'withdrawn')
    .map(({ paper, reason }) => ({
      paper_id: paper.id,
      title: paper.title,
      source: paper.source,
      reason,
    }))
  const prose = templateProse(
    {
      workspaceName,
      fetched: run.total_papers_fetched,
      passedScreening: run.total_papers_passed_screening,
      surfaced: surfaced.length,
      papers: surfaced,
    },
    lang,
  )
  return {
    run_id: run.id,
    workspace_id: run.workspace_id,
    date: editionDate(run),
    title: prose.title,
    in_brief: prose.in_brief,
    in_brief_source: 'template',
    funnel: {
      fetched: run.total_papers_fetched,
      passed_screening: run.total_papers_passed_screening,
      surfaced: surfaced.length,
    },
    papers: surfaced,
    exclusions,
    generated_at: run.completed_at,
  }
}

/**
 * Whether a run has a briefing to compose: it completed and passed
 * something. A search that found only papers already on file halts as
 * "completed" with no rows — a run, not a briefing (Home and the archive
 * leave it out too), so it gets no edition and a bare date link cannot land
 * on it. The run itself stays on /runs.
 */
export function briefs(run: Pick<PipelineRun, 'status' | 'total_papers_passed_screening'>) {
  return run.status === 'completed' && run.total_papers_passed_screening > 0
}

/**
 * The editions of one domain: one per run that briefs, newest by completion
 * first — a domain that ran twice in a day has two, and the URL's run id
 * tells them apart. `runs` may hold every status; the others are skipped.
 */
export function composeEditions(
  runs: readonly PipelineRun[],
  workspaceName: string,
  corpus: ReadonlyMap<string, ScoredPaper>,
  index: RunIndex | null,
  lang: Lang,
): Edition[] {
  return runs
    .filter(briefs)
    .map((run) => composeEdition(run, workspaceName, corpus, index, lang))
    .sort(byNewest)
}

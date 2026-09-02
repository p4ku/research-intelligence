/**
 * Briefings service. Source `composed` (default): one edition per completed
 * PipelineRun — funnel from the run's counters, papers/exclusions from the
 * scored corpus, prose from ./prose.ts templates (flagged 'template').
 * `django` = the requested editions endpoints. Server-only.
 */
import 'server-only'

import type { Lang } from '@/lib/i18n'
import { isPassed } from '@/lib/papers/map'
import { byValueDesc } from '@/lib/papers/select'
import type { ScoredPaper } from '@/lib/papers/types'
import { cache } from 'react'
import { django } from '../core/http'
import { paginate, type Page } from '../core/pagination'
import { problem, ProblemError } from '../core/problem'
import { sourceOf } from '../core/source'
import { assertUuid } from '../core/validate'
import { papers } from '../papers/service'
import type { PipelineRun } from '../pipeline-runs/schema'
import { runs } from '../pipeline-runs/service'
import { fixtureEditions } from './fixtures'
import { templateProse } from './prose'
import {
  edition,
  editionPage,
  type Edition,
  type EditionsQuery,
  type EditionSummary,
} from './schema'

function editionDate(run: PipelineRun): string {
  return run.completed_at ? run.completed_at.slice(0, 10) : run.run_date
}

function composeEdition(
  run: PipelineRun,
  workspaceName: string,
  corpus: ScoredPaper[],
  lang: Lang,
): Edition {
  const ofRun = corpus.filter((p) => p.pipeline_run_id === run.id)
  const surfaced = ofRun
    .filter((p) => isPassed(p.screening_status))
    .sort((a, b) => byValueDesc(a.signal_score, b.signal_score))
    .map((p) => ({
      id: p.id,
      title: p.title,
      authors: p.authors,
      source: p.source,
      signal_score: p.signal_score,
    }))
  const exclusions = ofRun
    .filter((p) => p.screening_status === 'rejected' || p.screening_status === 'withdrawn')
    .map((p) => ({
      paper_id: p.id,
      title: p.title,
      source: p.source,
      reason: p.screening_reasoning,
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

async function composeAll(workspaceId: string, lang: Lang): Promise<Edition[]> {
  const [completed, scored] = await Promise.all([
    runs.listAll(workspaceId, 'completed'),
    papers.listAll(workspaceId),
  ])
  if (!scored) return []
  const seen = new Set<string>()
  const editions: Edition[] = []
  for (const run of completed) {
    // Same-day reruns collapse to the latest (runs arrive newest first).
    const date = editionDate(run)
    if (seen.has(date)) continue
    seen.add(date)
    editions.push(composeEdition(run, scored.workspace.name, scored.papers, lang))
  }
  return editions
}

export const briefings = {
  /**
   * Every edition for a workspace, newest first, with exclusions. `lang` only
   * affects composed template prose. React-cached per request so the streamed
   * sections of one page share a single fetch.
   */
  listAll: cache(async (workspaceId: string, lang: Lang = 'en'): Promise<Edition[]> => {
    switch (sourceOf('briefings')) {
      case 'stub':
        return fixtureEditions.map((e) => ({ ...e, workspace_id: workspaceId }))
      case 'django': {
        const page = await django(
          `/api/workspaces/${workspaceId}/editions/?page_size=200`,
          editionPage,
        )
        // The list serves summaries; details carry exclusions.
        return page.results.map((summary: EditionSummary) => ({ ...summary, exclusions: [] }))
      }
      default:
        return composeAll(workspaceId, lang)
    }
  }),

  async list(query: EditionsQuery, lang: Lang = 'en'): Promise<Page<Omit<Edition, 'exclusions'>>> {
    const all = await briefings.listAll(query.workspace_id, lang)
    const summaries = all.map(({ exclusions: _exclusions, ...summary }) => summary)
    return paginate(summaries, query, '/bff/briefings', { workspace_id: query.workspace_id })
  },

  /** One edition by date; null when no completed run produced one. Cached per request. */
  getByDate: cache(
    async (workspaceId: string, date: string, lang: Lang = 'en'): Promise<Edition | null> => {
      if (sourceOf('briefings') === 'django') {
        try {
          return await django(
            `/api/workspaces/${assertUuid(workspaceId, 'workspace_id')}/editions/${date}/`,
            edition,
          )
        } catch (error) {
          if (error instanceof ProblemError && error.problem.status === 404) return null
          throw error
        }
      }
      return (await briefings.listAll(workspaceId, lang)).find((e) => e.date === date) ?? null
    },
  ),
}

export function assertDate(value: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    throw problem('validation', { detail: 'Edition dates are YYYY-MM-DD.' })
  }
  return value
}

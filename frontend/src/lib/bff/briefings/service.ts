/**
 * Briefings service. Source `composed` (default): one edition per completed
 * PipelineRun — funnel from the run's counters, papers/exclusions from the
 * scored corpus as that run recorded them (src/lib/papers/runs.ts), prose
 * from ./prose.ts templates (flagged 'template'). `django` = the requested
 * editions endpoints. Server-only.
 */
import 'server-only'

import type { Lang } from '@/lib/i18n'
import { isPassed } from '@/lib/papers/map'
import { papersOfRun, type RunIndex } from '@/lib/papers/runs'
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
import { workspaces } from '../workspaces/service'
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
    .map(({ paper, signal_score }) => ({
      id: paper.id,
      title: paper.title,
      authors: paper.authors,
      source: paper.source,
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

async function composeAll(workspaceId: string, lang: Lang): Promise<Edition[]> {
  const [completed, scored, index] = await Promise.all([
    runs.listAll(workspaceId, 'completed'),
    papers.listAll(workspaceId),
    papers.runIndex(),
  ])
  if (!scored) return []
  const corpus = new Map(scored.papers.map((p) => [p.id, p]))
  const seen = new Set<string>()
  const editions: Edition[] = []
  for (const run of completed) {
    // Same-day reruns collapse to the latest (runs arrive newest first).
    const date = editionDate(run)
    if (seen.has(date)) continue
    seen.add(date)
    editions.push(composeEdition(run, scored.workspace.name, corpus, index, lang))
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

  /**
   * Every edition across every domain the user belongs to, newest first. One
   * `listAll` per membership: free under `composed` (runs and corpus are
   * cached), one editions fetch per domain under `django`. Deduped by run so
   * the stub's repeated fixtures do not collide. Cached per request.
   */
  listEverywhere: cache(async (lang: Lang = 'en'): Promise<Edition[]> => {
    const memberships = await workspaces.listAll()
    const perWorkspace = await Promise.all(memberships.map((ws) => briefings.listAll(ws.id, lang)))
    const seen = new Set<string>()
    const merged = perWorkspace.flat().filter((e) => {
      if (seen.has(e.run_id)) return false
      seen.add(e.run_id)
      return true
    })
    const when = (e: Edition) => e.generated_at ?? `${e.date}T00:00:00Z`
    return merged.sort((a, b) => when(b).localeCompare(when(a)))
  }),

  async list(query: EditionsQuery, lang: Lang = 'en'): Promise<Page<Omit<Edition, 'exclusions'>>> {
    const all = query.workspace_id
      ? await briefings.listAll(query.workspace_id, lang)
      : await briefings.listEverywhere(lang)
    const summaries = all.map(({ exclusions: _exclusions, ...summary }) => summary)
    const extra: Record<string, string> = {}
    if (query.workspace_id) extra.workspace_id = query.workspace_id
    return paginate(summaries, query, '/bff/briefings', extra)
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

  /**
   * The edition for a day: in one domain when `workspaceId` is given, else
   * the newest edition any domain produced that day — which is what a link
   * from before domains were in the URL means. Cached per request.
   */
  findByDate: cache(
    async (date: string, lang: Lang = 'en', workspaceId?: string): Promise<Edition | null> => {
      if (workspaceId) return briefings.getByDate(workspaceId, date, lang)
      return (await briefings.listEverywhere(lang)).find((e) => e.date === date) ?? null
    },
  ),
}

export function assertDate(value: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    throw problem('validation', { detail: 'Edition dates are YYYY-MM-DD.' })
  }
  return value
}

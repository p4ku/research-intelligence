/**
 * Briefings service. Source `composed` (default): one edition per completed
 * PipelineRun — funnel from the run's counters, papers/exclusions from the
 * scored corpus as that run recorded them (src/lib/papers/runs.ts), prose
 * from ./prose.ts templates (flagged 'template'); the composition itself is
 * ./compose.ts, this file does the I/O. `django` = the requested editions
 * endpoints. Server-only.
 */
import 'server-only'

import type { Lang } from '@/lib/i18n'
import { papersOfRun } from '@/lib/papers/runs'
import { cache } from 'react'
import { django } from '../core/http'
import { paginate, type Page } from '../core/pagination'
import { problem, ProblemError } from '../core/problem'
import { sourceOf } from '../core/source'
import { assertUuid } from '../core/validate'
import { papers } from '../papers/service'
import { runs } from '../pipeline-runs/service'
import { workspaces } from '../workspaces/service'
import { composeEdition, composeEditions } from './compose'
import { fixtureEditions } from './fixtures'
import {
  edition,
  editionPage,
  type Edition,
  type EditionsQuery,
  type EditionSummary,
} from './schema'
import { byNewest, editionFor } from './select'

/** The I/O half of the `composed` source: the domain's runs, corpus and run index into `composeEditions`. */
async function composeAll(workspaceId: string, lang: Lang): Promise<Edition[]> {
  const [completed, scored, index] = await Promise.all([
    runs.listAll(workspaceId, 'completed'),
    papers.listAll(workspaceId),
    papers.runIndex(),
  ])
  if (!scored) return []
  const corpus = new Map(scored.papers.map((p) => [p.id, p]))
  return composeEditions(completed, scored.workspace.name, corpus, index, lang)
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
        return page.results.map((summary: EditionSummary) => ({
          ...summary,
          exclusions: [],
          papers: (summary.papers || []).map((p) => ({
            ...p,
            workspace_id: p.workspace_id || summary.workspace_id,
            pipeline_run_id: p.pipeline_run_id || summary.run_id,
          })),
        }))
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
    return merged.sort(byNewest)
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

  /**
   * One edition by date — the run's, when `runId` names one of that day's
   * runs, else the day's newest (see ./select.ts). Null when no completed
   * run produced one. Cached per request.
   */
  getByDate: cache(
    async (
      workspaceId: string,
      date: string,
      lang: Lang = 'en',
      runId?: string,
    ): Promise<Edition | null> => {
      if (sourceOf('briefings') === 'django') {
        try {
          const q = runId ? `?run_id=${assertUuid(runId, 'run_id')}` : ''
          return await django(
            `/api/workspaces/${assertUuid(workspaceId, 'workspace_id')}/editions/${date}/${q}`,
            edition,
          )
        } catch (error) {
          if (error instanceof ProblemError && error.problem.status === 404) return null
          throw error
        }
      }
      const found = editionFor(await briefings.listAll(workspaceId, lang), date, runId)
      if (!found) return null
      if (sourceOf('briefings') !== 'composed') return found
      // An edition at or past the corpus snapshot's cap composed from fewer
      // papers than its run wrote — none, or the cap cut through the run.
      // `listRun` reads them live in that case; recompose from what it gives.
      const [completed, scored, index, rows] = await Promise.all([
        runs.listAll(workspaceId, 'completed'),
        papers.listAll(workspaceId),
        papers.runIndex(),
        papers.listRun(workspaceId, found.run_id),
      ])
      const run = completed.find((r) => r.id === found.run_id)
      if (!run || !scored) return found
      const corpus = new Map(scored.papers.map((p) => [p.id, p]))
      const held = papersOfRun(run.id, corpus, index).length
      if (rows.length <= held) return found
      // Live rows are run-scoped: each carries this run's decision and
      // score already, so they are read as the corpus's own attribution.
      const live = new Map(rows.map((p) => [p.id, p]))
      return composeEdition(run, scored.workspace.name, live, null, lang)
    },
  ),

  /**
   * The edition for a day: in one domain when `workspaceId` is given, else
   * across every domain — and within that, the run `runId` names, else the
   * newest that day. That is what a link from before domains and runs were
   * in the URL means. Cached per request.
   */
  findByDate: cache(
    async (
      date: string,
      lang: Lang = 'en',
      workspaceId?: string,
      runId?: string,
    ): Promise<Edition | null> => {
      if (workspaceId) return briefings.getByDate(workspaceId, date, lang, runId)
      return editionFor(await briefings.listEverywhere(lang), date, runId)
    },
  ),
}

export function assertDate(value: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    throw problem('validation', { detail: 'Edition dates are YYYY-MM-DD.' })
  }
  return value
}

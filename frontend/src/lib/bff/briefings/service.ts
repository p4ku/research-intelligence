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
import { templateProse } from './prose'
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

export type BriefingScope = 'all' | 'included' | 'excluded'

export const briefings = {
  /**
   * Whether an edition's absence, or its emptiness, can be trusted. Under
   * `composed` the editions are cut from the per-user corpus, which the
   * paper cap may have cut through, so a run "with no papers" may only be
   * past the cap. Django's editions are never cut, so nothing is capped —
   * and the corpus is not read to say so: the ledger pages must neither
   * wait on the papers nor fail with them. Cached per request.
   */
  capped: cache(
    async (): Promise<boolean> =>
      sourceOf('briefings') === 'composed' ? papers.corpusTruncated() : false,
  ),

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
        const wsList = await workspaces.listAll().catch(() => [])
        const ws = wsList.find((w) => w.id === workspaceId)
        const fallbackWsName = ws?.name ?? 'Briefing'

        // Apply empty-run rule: runs that cleared nothing get no published briefing (PR #85)
        const briefed = page.results.filter((summary) => summary.funnel.passed_screening > 0)

        // The list serves summaries; details carry exclusions.
        return briefed.map((summary: EditionSummary) => {
          const papers = (summary.papers || []).map((p) => ({
            ...p,
            workspace_id: p.workspace_id || summary.workspace_id,
            pipeline_run_id: p.pipeline_run_id || summary.run_id,
          }))
          const workspaceName = summary.workspace_name || fallbackWsName
          let title = summary.title
          let in_brief = summary.in_brief
          if (summary.in_brief_source === 'template') {
            const prose = templateProse(
              {
                workspaceName,
                fetched: summary.funnel.fetched,
                passedScreening: summary.funnel.passed_screening,
                surfaced: summary.funnel.surfaced,
                papers,
              },
              lang,
            )
            title = prose.title
            in_brief = prose.in_brief
          }
          return {
            ...summary,
            title,
            in_brief,
            exclusions: [],
            papers,
          }
        })
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
   * `scope` can be 'all' (default), 'included' (surfaced only), or 'excluded' (exclusions only).
   */
  getByDate: cache(
    async (
      workspaceId: string,
      date: string,
      lang: Lang = 'en',
      runId?: string,
      scope?: BriefingScope,
      page?: number,
      pageSize?: number,
    ): Promise<Edition | null> => {
      if (sourceOf('briefings') === 'django') {
        try {
          const params = new URLSearchParams()
          if (runId) params.set('run_id', assertUuid(runId, 'run_id'))
          if (scope && scope !== 'all') params.set('scope', scope)
          if (page !== undefined) params.set('page', String(page))
          if (pageSize !== undefined) params.set('page_size', String(pageSize))
          const q = params.toString() ? `?${params.toString()}` : ''
          const ed = await django(
            `/api/workspaces/${assertUuid(workspaceId, 'workspace_id')}/editions/${date}/${q}`,
            edition,
          )
          // Empty-run rule: a run that cleared nothing has no published briefing (PR #85)
          if (ed.funnel.passed_screening <= 0) return null

          let title = ed.title
          let in_brief = ed.in_brief
          if (ed.in_brief_source === 'template') {
            const wsList = await workspaces.listAll().catch(() => [])
            const ws = wsList.find((w) => w.id === workspaceId)
            const workspaceName = ed.workspace_name || ws?.name || 'Briefing'
            const prose = templateProse(
              {
                workspaceName,
                fetched: ed.funnel.fetched,
                passedScreening: ed.funnel.passed_screening,
                surfaced: ed.funnel.surfaced,
                papers: ed.papers || [],
              },
              lang,
            )
            title = prose.title
            in_brief = prose.in_brief
          }
          return {
            ...ed,
            title,
            in_brief,
          }
        } catch (error) {
          if (error instanceof ProblemError && error.problem.status === 404) return null
          throw error
        }
      }
      const found = editionFor(await briefings.listAll(workspaceId, lang), date, runId)
      if (!found) return null
      let res: Edition = found
      if (sourceOf('briefings') !== 'composed') {
        if (scope === 'included') res = { ...found, exclusions: [] }
        else if (scope === 'excluded') res = { ...found, papers: [] }
      } else {
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
        if (!run || !scored) {
          res = found
        } else {
          const corpus = new Map(scored.papers.map((p) => [p.id, p]))
          const held = papersOfRun(run.id, corpus, index).length
          if (rows.length <= held) {
            if (scope === 'included') res = { ...found, exclusions: [] }
            else if (scope === 'excluded') res = { ...found, papers: [] }
            else res = found
          } else {
            // Live rows are run-scoped: each carries this run's decision and
            // score already, so they are read as the corpus's own attribution.
            const live = new Map(rows.map((p) => [p.id, p]))
            const composed = composeEdition(run, scored.workspace.name, live, null, lang)
            if (scope === 'included') res = { ...composed, exclusions: [] }
            else if (scope === 'excluded') res = { ...composed, papers: [] }
            else res = composed
          }
        }
      }
      if (page !== undefined && pageSize !== undefined) {
        const isExcluded = scope === 'excluded'
        const total = res.total ?? (isExcluded ? res.exclusions.length : res.papers.length)
        const start = (page - 1) * pageSize
        const paperSlice =
          res.papers.length > pageSize ? res.papers.slice(start, start + pageSize) : res.papers
        const exclusionSlice =
          isExcluded && res.exclusions.length > pageSize
            ? res.exclusions.slice(start, start + pageSize)
            : res.exclusions
        return {
          ...res,
          papers: paperSlice,
          exclusions: exclusionSlice,
          total,
          page,
          page_size: pageSize,
          total_pages: Math.max(1, Math.ceil(total / pageSize)),
        }
      }
      return res
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
      scope?: BriefingScope,
      page?: number,
      pageSize?: number,
    ): Promise<Edition | null> => {
      if (workspaceId)
        return briefings.getByDate(workspaceId, date, lang, runId, scope, page, pageSize)
      const found = editionFor(await briefings.listEverywhere(lang), date, runId)
      if (!found) return null
      let res: Edition = found
      if (scope === 'included') res = { ...found, exclusions: [] }
      else if (scope === 'excluded') res = { ...found, papers: [] }
      if (page !== undefined && pageSize !== undefined) {
        const isExcluded = scope === 'excluded'
        const total = res.total ?? (isExcluded ? res.exclusions.length : res.papers.length)
        const start = (page - 1) * pageSize
        const paperSlice =
          res.papers.length > pageSize ? res.papers.slice(start, start + pageSize) : res.papers
        const exclusionSlice =
          isExcluded && res.exclusions.length > pageSize
            ? res.exclusions.slice(start, start + pageSize)
            : res.exclusions
        return {
          ...res,
          papers: paperSlice,
          exclusions: exclusionSlice,
          total,
          page,
          page_size: pageSize,
          total_pages: Math.max(1, Math.ceil(total / pageSize)),
        }
      }
      return res
    },
  ),
}

export function assertDate(value: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    throw problem('validation', { detail: 'Edition dates are YYYY-MM-DD.' })
  }
  return value
}

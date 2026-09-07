/**
 * Papers service — the seam every papers consumer goes through.
 *
 * Sources:
 * - `composed` (default): built from today's `/api/papers/` + `/api/extractions/`
 *   + `/api/workspaces/` (see ./compose.ts).
 * - `django`: the requested scorecard endpoints (validated pass-through).
 * - `stub`: contract-shaped fixtures.
 *
 * Server-only; always returns contract shapes (src/lib/bff/papers/schema.ts).
 */
import 'server-only'

import { byValueAsc, byValueDesc, dimensionByKey } from '@/lib/papers/select'
import { parseQuery, rank } from '@/lib/search/match'
import { cache } from 'react'
import * as z from 'zod'
import { django } from '../core/http'
import { paginate, type Page } from '../core/pagination'
import { problem, ProblemError } from '../core/problem'
import { sourceOf } from '../core/source'
import { assertUuid } from '../core/validate'
import { workspace, type WorkspaceSummary } from '../workspaces/schema'
import { workspaces } from '../workspaces/service'
import { composeGet, composeListAll } from './compose'
import { fixturePapers, fixtureWorkspace } from './fixtures'
import { paperPage, scoredPaper, type PapersQuery, type ScoredPaper } from './schema'

export interface WorkspacePapers {
  workspace: WorkspaceSummary
  papers: ScoredPaper[]
}

/** The unified corpus: every domain the user belongs to and every paper in them. */
export interface CorpusPapers {
  workspaces: WorkspaceSummary[]
  papers: ScoredPaper[]
}

const detailResponse = z.object({ workspace, paper: scoredPaper })

/** The requested endpoint, drained page by page (the UI holds the whole corpus in memory anyway). */
async function djangoPapersOf(workspaceId: string): Promise<ScoredPaper[]> {
  assertUuid(workspaceId, 'workspace_id')
  const papers: ScoredPaper[] = []
  let page = 1
  for (;;) {
    const result = await django(
      `/api/workspaces/${workspaceId}/papers/?page=${page}&page_size=200`,
      paperPage,
    )
    papers.push(...result.results)
    if (!result.next || page >= 50) break
    page += 1
  }
  return papers
}

async function djangoListAll(workspaceId: string): Promise<WorkspacePapers | null> {
  // Only a genuine 404 (workspace gone) may become null; an outage must
  // throw, or a fetched corpus gets presented as "no membership" (#2).
  const [papers, ws] = await Promise.all([
    djangoPapersOf(workspaceId),
    django(`/api/workspaces/${workspaceId}/`, workspace).catch((error: unknown) => {
      if (error instanceof ProblemError && error.problem.status === 404) return null
      throw error
    }),
  ])
  return ws ? { workspace: ws, papers } : null
}

function stubListAll(workspaceId: string): WorkspacePapers {
  return {
    workspace: { ...fixtureWorkspace, id: workspaceId },
    papers: fixturePapers.map((p) => ({ ...p, workspace_id: workspaceId })),
  }
}

function order(papers: ScoredPaper[], ordering: string): ScoredPaper[] {
  const desc = ordering.startsWith('-')
  const key = desc ? ordering.slice(1) : ordering
  const sorted = [...papers]
  if (key === 'created_at') {
    sorted.sort((a, b) => a.created_at.localeCompare(b.created_at))
    if (desc) sorted.reverse()
    return sorted
  }
  const value = (p: ScoredPaper): number | null =>
    key === 'signal_score' ? p.signal_score : (dimensionByKey(p, key.slice(4))?.value ?? null)
  sorted.sort((a, b) => (desc ? byValueDesc(value(a), value(b)) : byValueAsc(value(a), value(b))))
  return sorted
}

export const papers = {
  /**
   * The whole workspace corpus + its workspace summary; null when not visible.
   * React-cached per request so sibling streamed sections share one fetch.
   */
  listAll: cache(async (workspaceId: string): Promise<WorkspacePapers | null> => {
    switch (sourceOf('papers')) {
      case 'stub':
        return stubListAll(workspaceId)
      case 'django':
        return djangoListAll(workspaceId)
      default:
        return composeListAll(workspaceId)
    }
  }),

  /**
   * Every paper across every domain the user belongs to, with the domain
   * summaries (definitions, scales) the lists need for their sort options.
   * Under `composed` the fan-out is free — the raw lists are cached and only
   * the per-domain scoring repeats; under `django` it is one corpus fetch per
   * domain, with the summaries taken from the memberships list instead of a
   * second GET each. Cached per request.
   */
  listEverywhere: cache(async (): Promise<CorpusPapers> => {
    const memberships = await workspaces.listAll()
    const perWorkspace = await Promise.all(
      memberships.map(
        async (ws): Promise<WorkspacePapers | null> =>
          sourceOf('papers') === 'django'
            ? { workspace: ws, papers: await djangoPapersOf(ws.id) }
            : papers.listAll(ws.id),
      ),
    )
    const seen = new Set<string>()
    const merged: ScoredPaper[] = []
    const summaries: WorkspaceSummary[] = []
    for (const scored of perWorkspace) {
      // A membership the corpus cannot see is a backend inconsistency, not an
      // outage (that would have thrown): it drops out rather than failing the
      // whole page. Papers are deduped by id (the stub repeats its fixtures).
      if (!scored) continue
      summaries.push(scored.workspace)
      for (const paper of scored.papers) {
        if (seen.has(paper.id)) continue
        seen.add(paper.id)
        merged.push(paper)
      }
    }
    return { workspaces: summaries, papers: merged }
  }),

  /** The paginated HTTP face: screening filter, ordering, search; one domain or all. */
  async list(query: PapersQuery): Promise<Page<ScoredPaper>> {
    const all = query.workspace_id
      ? await papers.listAll(query.workspace_id)
      : await papers.listEverywhere()
    if (!all) throw problem('not-found', { detail: 'No such workspace in your memberships.' })
    let rows = all.papers
    if (query.screening === 'passed') {
      rows = rows.filter((p) =>
        ['abstract_passed', 'full_text_passed', 'accepted'].includes(p.screening_status),
      )
    } else if (query.screening !== 'all') {
      rows = rows.filter((p) => p.screening_status === query.screening)
    }
    if (query.search) {
      // The same matcher as the Home typeahead and the Papers page filter.
      const parsed = parseQuery(query.search)
      rows = rows.filter((p) => rank(p, parsed) !== null)
    }
    rows = order(rows, query.ordering)
    const extra: Record<string, string> = { screening: query.screening, ordering: query.ordering }
    if (query.workspace_id) extra.workspace_id = query.workspace_id
    if (query.search) extra.search = query.search
    return paginate(rows, query, '/bff/papers', extra)
  },

  /**
   * One paper with its workspace; null when missing or not visible. Cached per
   * request: generateMetadata and the page's streamed sections share the call.
   */
  get: cache(
    async (id: string): Promise<{ workspace: WorkspaceSummary; paper: ScoredPaper } | null> => {
      switch (sourceOf('papers')) {
        case 'stub': {
          const paper = fixturePapers.find((p) => p.id === id) ?? null
          return paper ? { workspace: fixtureWorkspace, paper } : null
        }
        case 'django':
          try {
            return await django(
              `/api/papers/${assertUuid(id, 'paper id')}/scorecard/`,
              detailResponse,
            )
          } catch (error) {
            if (error instanceof ProblemError && error.problem.status === 404) return null
            throw error
          }
        default:
          return composeGet(id)
      }
    },
  ),
}

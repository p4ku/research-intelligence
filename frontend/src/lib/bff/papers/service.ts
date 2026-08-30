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
import * as z from 'zod'
import { django } from '../core/http'
import { paginate, type Page } from '../core/pagination'
import { problem, ProblemError } from '../core/problem'
import { assertUuid } from '../core/validate'
import { sourceOf } from '../core/source'
import { workspace, type WorkspaceSummary } from '../workspaces/schema'
import { composeGet, composeListAll } from './compose'
import { fixturePapers, fixtureWorkspace } from './fixtures'
import { paperPage, scoredPaper, type PapersQuery, type ScoredPaper } from './schema'

export interface WorkspacePapers {
  workspace: WorkspaceSummary
  papers: ScoredPaper[]
}

const detailResponse = z.object({ workspace, paper: scoredPaper })

async function djangoListAll(workspaceId: string): Promise<WorkspacePapers | null> {
  assertUuid(workspaceId, 'workspace_id')
  // The requested endpoint, drained page by page (the UI's composed path
  // holds the whole corpus in memory anyway; server-side filtering starts
  // once this endpoint exists).
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
  const [ws] = await Promise.all([
    django(`/api/workspaces/${workspaceId}/`, workspace).catch(() => null),
  ])
  return ws ? { workspace: ws, papers } : null
}

function stubListAll(workspaceId: string): WorkspacePapers {
  return {
    workspace: { ...fixtureWorkspace, id: workspaceId },
    papers: fixturePapers.map((p) => ({ ...p, workspace_id: workspaceId })),
  }
}

function matches(paper: ScoredPaper, search: string): boolean {
  const q = search.toLowerCase()
  return [paper.title, paper.abstract, paper.authors_raw, paper.arxiv_id ?? '', paper.doi ?? '']
    .join('\n')
    .toLowerCase()
    .includes(q)
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
  /** The whole workspace corpus + its workspace summary; null when not visible. */
  async listAll(workspaceId: string): Promise<WorkspacePapers | null> {
    switch (sourceOf('papers')) {
      case 'stub':
        return stubListAll(workspaceId)
      case 'django':
        return djangoListAll(workspaceId)
      default:
        return composeListAll(workspaceId)
    }
  },

  /** The paginated HTTP face: screening filter, ordering, search. */
  async list(query: PapersQuery): Promise<Page<ScoredPaper>> {
    const all = await papers.listAll(query.workspace_id)
    if (!all) throw problem('not-found', { detail: 'No such workspace in your memberships.' })
    let rows = all.papers
    if (query.screening === 'passed') {
      rows = rows.filter((p) =>
        ['abstract_passed', 'full_text_passed', 'accepted'].includes(p.screening_status),
      )
    } else if (query.screening !== 'all') {
      rows = rows.filter((p) => p.screening_status === query.screening)
    }
    if (query.search) rows = rows.filter((p) => matches(p, query.search!))
    rows = order(rows, query.ordering)
    const extra: Record<string, string> = {
      workspace_id: query.workspace_id,
      screening: query.screening,
      ordering: query.ordering,
    }
    if (query.search) extra.search = query.search
    return paginate(rows, query, '/bff/papers', extra)
  },

  /** One paper with its workspace; null when missing or not visible. */
  async get(id: string): Promise<{ workspace: WorkspaceSummary; paper: ScoredPaper } | null> {
    switch (sourceOf('papers')) {
      case 'stub': {
        const paper = fixturePapers.find((p) => p.id === id) ?? null
        return paper ? { workspace: fixtureWorkspace, paper } : null
      }
      case 'django':
        try {
          return await django(`/api/papers/${assertUuid(id, 'paper id')}/scorecard/`, detailResponse)
        } catch (error) {
          if (error instanceof ProblemError && error.problem.status === 404) return null
          throw error
        }
      default:
        return composeGet(id)
    }
  },
}

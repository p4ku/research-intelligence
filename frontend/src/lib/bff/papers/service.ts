/**
 * Papers service — the seam every papers consumer goes through.
 *
 * Sources:
 * - `django` (default): Django's scorecard endpoints. The lists come from
 *   the user's scored corpus (../corpus/snapshot.ts), one drain per domain
 *   per corpus version held across requests; a run's papers and one paper
 *   are live reads. `composed` reads the same scorecard and, for the run
 *   index, the raw lists too (docs/scorecard-backlog.md item 15).
 * - `stub`: contract-shaped fixtures.
 *
 * Server-only; always returns contract shapes (src/lib/bff/papers/schema.ts).
 */
import 'server-only'

import type { PaperDTO } from '@/lib/api/types'
import { isPassed } from '@/lib/papers/map'
import { indexRuns, papersOfRun, type RunIndex } from '@/lib/papers/runs'
import { cache } from 'react'
import * as z from 'zod'
import { drain } from '../core/drain'
import { django, djangoPage } from '../core/http'
import { paginate } from '../core/pagination'
import { problem, ProblemError } from '../core/problem'
import { sourceOf } from '../core/source'
import { assertUuid } from '../core/validate'
import { SCORECARD_PAGE_SIZE, scoredCorpus } from '../corpus/snapshot'
import { stars } from '../stars/service'
import type { WorkspaceSummary } from '../workspaces/schema'
import { workspaces } from '../workspaces/service'
import { listPapersRaw } from './compose'
import { applyPapersQuery, corpusFacets } from './filter'
import { fixturePapers, fixtureWorkspace } from './fixtures'
import {
  paperList,
  papersQuery,
  scoredPaper,
  type PapersList,
  type PapersQuery,
  type ScoredPaper,
} from './schema'
import { scorecardQuery } from './scorecard-query'

export interface WorkspacePapers {
  workspace: WorkspaceSummary
  papers: ScoredPaper[]
}

/** The unified corpus: every domain the user belongs to and every paper in them. */
export interface CorpusPapers {
  workspaces: WorkspaceSummary[]
  papers: ScoredPaper[]
  /** Set when the per-user cap dropped older papers (../corpus/scored.ts). */
  truncated?: { kept: number; total: number }
}

const scorecardWorkspace = z
  .object({
    id: z.string(),
    name: z.string(),
    user_role: z.string().nullable().optional().default(null),
    definitions: z
      .array(
        z
          .object({
            id: z.string(),
            name: z.string(),
            key: z.string(),
            is_active: z.boolean().optional().default(true),
            is_trl: z.boolean().optional().default(false),
            order: z.number().optional(),
            max: z.number().nullable().optional().default(null),
          })
          .passthrough(),
      )
      .optional()
      .default([]),
    scrapers: z.array(z.any()).optional().default([]),
    scrapers_count: z.number().optional().default(0),
    digest_schedule: z.string().nullable().optional().default(null),
    screening_llm_model: z.string().nullable().optional().default(null),
    llm_provider: z.string().nullable().optional().default(null),
    created_at: z
      .string()
      .optional()
      .default(() => new Date().toISOString()),
  })
  .passthrough()

const detailResponse = z.object({ workspace: scorecardWorkspace, paper: scoredPaper }).passthrough()

function stubListAll(workspaceId: string): WorkspacePapers {
  return {
    workspace: { ...fixtureWorkspace, id: workspaceId },
    papers: fixturePapers.map((p) => ({ ...p, workspace_id: workspaceId })),
  }
}

/** The reader's stars, once per request: the sidebar and the list share it. */
const starredPapers = cache(() => stars.get())

/** The run index is a pure function of the raw list, which lives across requests — so does the index. */
const runIndexOf = new WeakMap<PaperDTO[], RunIndex>()

/** Pages of one run's scorecard read at most (10,000 papers at 200 a page) — a bound, not a cap. */
const RUN_PAGES_CEILING = 50

export const papers = {
  /**
   * The whole workspace corpus + its workspace summary; null when the user is
   * not a member (a hidden domain included). The rows are the scored corpus's,
   * the summary the memberships list's, so a warm corpus answers with no
   * upstream call. React-cached per request so sibling streamed sections
   * share one read. An outage throws: a fetched corpus must never read as
   * "no membership".
   */
  listAll: cache(async (workspaceId: string): Promise<WorkspacePapers | null> => {
    if (sourceOf('papers') === 'stub') return stubListAll(workspaceId)
    assertUuid(workspaceId, 'workspace_id')
    const [workspace, corpus] = await Promise.all([workspaces.get(workspaceId), scoredCorpus()])
    if (!workspace) return null
    return { workspace, papers: corpus.byWorkspace.get(workspaceId) ?? [] }
  }),

  /**
   * Every paper across every domain the user belongs to, with the domain
   * summaries (definitions, scales) the lists need for their sort options.
   * One read of the scored corpus, whatever the number of domains. Papers
   * are deduped by id (the stub repeats its fixtures). Cached per request.
   */
  listEverywhere: cache(async (): Promise<CorpusPapers> => {
    const memberships = await workspaces.listAll()
    const seen = new Set<string>()
    const merged: ScoredPaper[] = []
    const add = (rows: ScoredPaper[]) => {
      for (const paper of rows) {
        if (seen.has(paper.id)) continue
        seen.add(paper.id)
        merged.push(paper)
      }
    }
    if (sourceOf('papers') === 'stub') {
      for (const ws of memberships) add(stubListAll(ws.id).papers)
      return { workspaces: memberships, papers: merged }
    }
    const corpus = await scoredCorpus()
    for (const ws of memberships) add(corpus.byWorkspace.get(ws.id) ?? [])
    return { workspaces: memberships, papers: merged, truncated: corpus.truncated }
  }),

  /**
   * Every run's own record of every paper (src/lib/papers/runs.ts), for the
   * readers that need a paper as one run saw it rather than as it stands
   * today — the briefings. Only the `composed` source sees the per-run
   * metrics; the others return null and the corpus's own attribution is all
   * there is. Cached per request, over the same snapshot as before.
   */
  runIndex: cache(async (): Promise<RunIndex | null> => {
    if (sourceOf('papers') !== 'composed') return null
    const raw = await listPapersRaw()
    let index = runIndexOf.get(raw)
    if (!index) runIndexOf.set(raw, (index = indexRuns(raw)))
    return index
  }),

  /**
   * Whether the per-user cap dropped older papers from the scored corpus
   * (../corpus/scored.ts). A reader deciding that a run "has no papers"
   * must ask first: past the cap, absence is not evidence. Cached per request.
   */
  corpusTruncated: cache(async (): Promise<boolean> => {
    if (sourceOf('papers') === 'stub') return false
    return Boolean((await scoredCorpus()).truncated)
  }),

  /**
   * The papers one run wrote, scored — read live from Django's run-scoped
   * scorecard, a page at a time. Live on purpose: the corpus's rows carry
   * each paper's newest run, not every run that saw it (src/lib/papers/runs.ts),
   * and a run-scoped read carries that run's decision and score. Empty when
   * the workspace is gone. Cached per request.
   *
   * `screening` narrows the read to the papers the run passed. A reader that
   * only wants the rows a briefing lists must say so: the run filter alone
   * returns everything the run screened, and a scorecard row weighs ~19 KB,
   * so a 771-screened run costs ~15 MB to answer a question about 23 papers.
   * A primitive argument, not an options object, so the React cache still
   * dedupes the call across a page's streamed sections.
   */
  listRun: cache(
    async (workspaceId: string, runId: string, screening?: 'passed'): Promise<ScoredPaper[]> => {
      if (sourceOf('papers') === 'stub') {
        const [scored, index] = await Promise.all([papers.listAll(workspaceId), papers.runIndex()])
        const corpus = new Map((scored?.papers ?? []).map((p) => [p.id, p]))
        // The run's own decision, not the paper's current one: `papersOfRun`
        // carries both and they differ once a paper has been through two runs.
        return papersOfRun(runId, corpus, index)
          .filter((r) => screening !== 'passed' || isPassed(r.status))
          .map((r) => r.paper)
      }
      assertUuid(workspaceId, 'workspace_id')
      assertUuid(runId, 'run id')
      const query = scorecardQuery({ runId, screening })
      try {
        const rows = await drain(
          (page, size) =>
            djangoPage(
              `/api/workspaces/${workspaceId}/scorecard/?${query}`,
              scoredPaper,
              page,
              size,
            ),
          {
            pageSize: SCORECARD_PAGE_SIZE,
            maxItems: Number.POSITIVE_INFINITY,
            maxPages: RUN_PAGES_CEILING,
            id: (p) => p.id,
          },
        )
        if (rows.cutShort) {
          console.warn(
            '[bff] run %s: stopped after %d pages of its scorecard; some papers are missing',
            runId,
            rows.pages,
          )
        }
        return rows.items
      } catch (error) {
        if (error instanceof ProblemError && error.problem.status === 404) return []
        throw error
      }
    },
  ),

  /**
   * The Papers page's HTTP face: one page of the corpus under every control,
   * with the rail's facets. The whole corpus is read even for one domain —
   * it is held across requests and the facets span it anyway — and the
   * filters themselves are pure (./filter.ts).
   */
  async list(query: PapersQuery): Promise<PapersList> {
    if (sourceOf('papers') === 'django') {
      const params = new URLSearchParams()
      for (const [key, value] of Object.entries(query)) {
        if (value !== undefined && value !== null && value !== '') {
          params.set(key, String(value))
        }
      }
      const qs = params.toString()
      return await django(`/api/papers/scorecard/${qs ? `?${qs}` : ''}`, paperList)
    }

    const corpus = await papers.listEverywhere()
    if (query.workspace_id && !corpus.workspaces.some((w) => w.id === query.workspace_id)) {
      throw problem('not-found', { detail: 'No such workspace in your memberships.' })
    }
    const starred = new Set((await starredPapers()).papers)
    const { rows, hiddenByScreening } = applyPapersQuery(corpus, query, starred)
    // Every non-default control rides on next/previous, so a consumer walking
    // the links stays inside the same view.
    const extra: Record<string, string> = {}
    const defaults = papersQuery.parse({})
    for (const [key, value] of Object.entries(query)) {
      if (key === 'page' || key === 'page_size' || value === undefined) continue
      if (value !== defaults[key as keyof typeof defaults]) extra[key] = String(value)
    }
    return {
      ...paginate(rows, query, '/bff/papers', extra),
      facets: {
        ...corpusFacets(corpus, starred),
        hidden_by_screening: hiddenByScreening,
        truncated: corpus.truncated
          ? { shown: corpus.truncated.kept, total: corpus.truncated.total }
          : null,
      },
    }
  },

  /**
   * One paper with its workspace; null when missing or not visible. A live
   * read: a paper ingested a moment ago is readable, a missing id is a
   * genuine 404. Cached per request: generateMetadata and the page's
   * streamed sections share the call.
   */
  get: cache(
    async (
      id: string,
      runId?: string,
    ): Promise<{ workspace: WorkspaceSummary; paper: ScoredPaper } | null> => {
      if (sourceOf('papers') === 'stub') {
        const paper = fixturePapers.find((p) => p.id === id) ?? null
        return paper ? { workspace: fixtureWorkspace, paper } : null
      }
      try {
        const query = runId ? `?pipeline_run=${encodeURIComponent(runId)}` : ''
        return await django(
          `/api/papers/${assertUuid(id, 'paper id')}/scorecard/${query}`,
          detailResponse,
        )
      } catch (error) {
        if (error instanceof ProblemError && error.problem.status === 404) return null
        throw error
      }
    },
  ),
}

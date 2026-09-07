/**
 * The `composed` source for papers: assembles `ScoredPaper` from the three
 * unfiltered, unpaginated endpoints Django offers today (papers, extractions,
 * workspaces), exactly the logic we are asking the backend to absorb into a
 * scorecard endpoint. The pure derivation rules live in src/lib/papers/map.ts
 * — that file (with map.test.ts as acceptance cases) is the port reference.
 * Server-only.
 */
import 'server-only'

import type { ExtractionDTO } from '@/lib/api/types'
import {
  corpusMaxima,
  definitionContexts,
  toScoredPaper,
  toWorkspaceSummary,
} from '@/lib/papers/map'
import type { ScoredPaper, WorkspaceSummary } from '@/lib/papers/types'
import { cache } from 'react'
import { django } from '../core/http'
import { ProblemError } from '../core/problem'
import { assertUuid } from '../core/validate'
import { corpusSnapshot } from '../corpus/snapshot'
import { listWorkspacesRaw } from '../workspaces/service'
import { paperDTO } from './upstream'

// The lists come from the user's corpus snapshot (../corpus/snapshot.ts),
// held across requests; a single paper is always a live GET, so a missing
// id is a genuine 404 and a paper ingested a moment ago is readable.
export const listPapersRaw = cache(async () => (await corpusSnapshot()).papers)
export const listExtractionsRaw = cache(async () => (await corpusSnapshot()).extractions)
export const getPaperRaw = cache(async (id: string) => {
  try {
    return await django(`/api/papers/${assertUuid(id, 'paper id')}/`, paperDTO)
  } catch (error) {
    if (error instanceof ProblemError && error.problem.status === 404) return null
    throw error
  }
})

async function workspaceContext(workspaceId: string) {
  const [workspaces, extractions] = await Promise.all([listWorkspacesRaw(), listExtractionsRaw()])
  const ws = workspaces.find((w) => w.id === workspaceId)
  if (!ws) return null
  const wsExtractions = extractions.filter((e) => e.workspace === workspaceId)
  const maxima = corpusMaxima(ws.extraction_definitions, wsExtractions)
  return {
    summary: toWorkspaceSummary(ws, maxima),
    contexts: definitionContexts(ws.extraction_definitions, maxima),
    extractionsByPaper: groupBy(wsExtractions, (e) => e.paper),
  }
}

/** Every paper in a workspace, scored against its definitions. Unsorted. */
export async function composeListAll(
  workspaceId: string,
): Promise<{ workspace: WorkspaceSummary; papers: ScoredPaper[] } | null> {
  const [ctx, papers] = await Promise.all([workspaceContext(workspaceId), listPapersRaw()])
  if (!ctx) return null
  return {
    workspace: ctx.summary,
    papers: papers
      .filter((p) => p.workspace === workspaceId)
      .map((p) => toScoredPaper(p, ctx.extractionsByPaper.get(p.id) ?? [], ctx.contexts)),
  }
}

/** One paper with its workspace's definitions; null when missing or not visible. */
export async function composeGet(
  id: string,
): Promise<{ workspace: WorkspaceSummary; paper: ScoredPaper } | null> {
  // The snapshot does not depend on the paper, so the two loads overlap.
  const [raw] = await Promise.all([getPaperRaw(id), corpusSnapshot()])
  if (!raw) return null
  const ctx = await workspaceContext(raw.workspace)
  if (!ctx) return null
  return {
    workspace: ctx.summary,
    paper: toScoredPaper(raw, ctx.extractionsByPaper.get(raw.id) ?? [], ctx.contexts),
  }
}

function groupBy(items: ExtractionDTO[], key: (item: ExtractionDTO) => string) {
  const map = new Map<string, ExtractionDTO[]>()
  for (const item of items) {
    const k = key(item)
    const bucket = map.get(k)
    if (bucket) bucket.push(item)
    else map.set(k, [item])
  }
  return map
}

/**
 * Scoring service (read-only). Source `composed` (default): the snippet and
 * the worked example come from the newest scored paper's
 * signal_score_details (the workspace serializer does not expose
 * signal_score_code); variables from the workspace's definitions; weights are
 * an even placeholder flagged 'stub' until the backend exposes real ones.
 * Server-only.
 */
import 'server-only'

import { django } from '../core/http'
import { problem } from '../core/problem'
import { sourceOf } from '../core/source'
import { papers } from '../papers/service'
import { fixtureScoring } from './fixtures'
import { workspaceScoring, type WorkspaceScoring } from './schema'

async function compose(workspaceId: string): Promise<WorkspaceScoring> {
  const scored = await papers.listAll(workspaceId)
  if (!scored) throw problem('not-found', { detail: 'No such workspace in your memberships.' })

  const variables = scored.workspace.definitions
    .filter((d) => d.is_active)
    .map((d) => ({ key: d.key, definition_id: d.id, name: d.name, max: d.max, is_trl: d.is_trl }))

  // The best-scored paper with an evaluation record makes the clearest
  // worked example (ties broken by recency).
  const newestScored = scored.papers
    .filter((p) => p.signal_score_details?.code_snippet)
    .sort(
      (a, b) =>
        (b.signal_score ?? -1) - (a.signal_score ?? -1) ||
        b.created_at.localeCompare(a.created_at),
    )[0]
  const details = newestScored?.signal_score_details ?? null

  // Even placeholder split over the scoring variables, honestly flagged —
  // the real weights live inside the backend's snippet.
  const weights = variables.map((v) => ({
    key: v.key,
    definition_id: v.definition_id,
    name: v.name,
    weight: variables.length > 0 ? Math.round(1000 / variables.length) / 10 : 0,
  }))

  return {
    workspace_id: workspaceId,
    code: details?.code_snippet ?? null,
    code_source: 'latest_metric',
    variables,
    weights,
    weights_source: 'stub',
    example: newestScored
      ? {
          paper_id: newestScored.id,
          title: newestScored.title,
          signal_score: newestScored.signal_score,
          variables: details?.variables ?? {},
        }
      : null,
  }
}

export const scoring = {
  async get(workspaceId: string): Promise<WorkspaceScoring> {
    switch (sourceOf('scoring')) {
      case 'stub':
        return { ...fixtureScoring, workspace_id: workspaceId }
      case 'django':
        return django(`/api/workspaces/${workspaceId}/scoring/`, workspaceScoring)
      default:
        return compose(workspaceId)
    }
  },
}

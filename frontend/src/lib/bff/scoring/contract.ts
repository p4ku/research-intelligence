/** Scoring contract registry entries. Pure. */
import type { Operation } from '../core/contract-types'
import { workspaceScoring } from './schema'

export const scoringOperations: Operation[] = [
  {
    id: 'scoring.get.desired',
    resource: 'scoring',
    face: 'django',
    kind: 'desired',
    method: 'GET',
    path: '/api/workspaces/{workspace_id}/scoring/',
    summary:
      "Read-only: the workspace's signal_score_code snippet (currently unserialized), its variables, and a structured weights list kept alongside the code. Users never edit — the formula stays backend-owned.",
    responses: { 200: workspaceScoring },
    probe: { requires: ['workspace_id'] },
  },
  {
    id: 'scoring.get.bff',
    resource: 'scoring',
    face: 'bff',
    kind: 'bff',
    method: 'GET',
    path: '/bff/scoring',
    summary: 'How this workspace scores papers (?workspace_id=).',
    responses: { 200: workspaceScoring },
  },
]

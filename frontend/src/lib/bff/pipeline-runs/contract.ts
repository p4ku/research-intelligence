/** Pipeline-runs contract registry entries. Pure. */
import * as z from 'zod'
import type { Operation } from '../core/contract-types'
import { runPage, runsQuery } from './schema'
import { pipelineRunDTO, pipelineRunDetailDTO } from './upstream'

export const pipelineRunsOperations: Operation[] = [
  {
    id: 'pipeline-runs.list.current',
    resource: 'pipeline-runs',
    face: 'django',
    kind: 'current',
    method: 'GET',
    path: '/api/pipeline-runs/',
    summary:
      "Every run across the user's workspaces (bare array, newest first; ?workspace= and ?status= supported) — the BFF consumes it unfiltered.",
    responses: { 200: z.array(pipelineRunDTO) },
  },
  {
    id: 'pipeline-runs.list.desired',
    supersedes: 'pipeline-runs.list.current',
    resource: 'pipeline-runs',
    face: 'django',
    kind: 'desired',
    method: 'GET',
    path: '/api/pipeline-runs/?workspace={workspace_id}',
    summary: 'Same endpoint, paginated with ?ordering=. Low priority.',
    query: runsQuery.omit({ workspace_id: true }),
    responses: { 200: runPage },
    probe: { requires: ['workspace_id'] },
  },
  {
    id: 'pipeline-runs.get.current',
    resource: 'pipeline-runs',
    face: 'django',
    kind: 'current',
    method: 'GET',
    path: '/api/pipeline-runs/{run_id}/',
    summary: 'One run: the list shape plus per-run counts, storage stats and embedded steps.',
    responses: { 200: pipelineRunDetailDTO },
    probe: { requires: ['run_id'] },
  },
  {
    id: 'pipeline-runs.list.bff',
    resource: 'pipeline-runs',
    face: 'bff',
    kind: 'bff',
    method: 'GET',
    path: '/bff/pipeline-runs',
    summary:
      'Paginated runs in the contract shape; ?workspace_id= narrows to one domain, otherwise every domain the user belongs to.',
    query: runsQuery,
    responses: { 200: runPage },
  },
]

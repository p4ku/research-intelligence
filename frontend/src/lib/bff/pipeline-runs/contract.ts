/** Pipeline-runs contract registry entries. Pure. */
import * as z from 'zod'
import type { Operation } from '../core/contract-types'
import { runPage, runsQuery } from './schema'
import { pipelineRunDTO } from './upstream'

export const pipelineRunsOperations: Operation[] = [
  {
    id: 'pipeline-runs.list.current',
    resource: 'pipeline-runs',
    face: 'django',
    kind: 'current',
    method: 'GET',
    path: '/api/pipeline-runs/?workspace={workspace_id}',
    summary: 'Runs for a workspace (bare array, newest first; ?status= supported).',
    responses: { 200: z.array(pipelineRunDTO) },
    probe: { requires: ['workspace_id'] },
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
    id: 'pipeline-runs.list.bff',
    resource: 'pipeline-runs',
    face: 'bff',
    kind: 'bff',
    method: 'GET',
    path: '/bff/pipeline-runs',
    summary: 'Paginated runs for a workspace in the contract shape.',
    query: runsQuery,
    responses: { 200: runPage },
  },
]

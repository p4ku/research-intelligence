/** Pipeline-runs contract registry entries. Pure. */
import * as z from 'zod'
import { edition } from '../briefings/schema'
import type { Operation } from '../core/contract-types'
import { runPage, runsOverview, runsQuery } from './schema'
import { pipelineRunDTO, pipelineRunDetailDTO } from './upstream'

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
    id: 'pipeline-runs.list-all.current',
    resource: 'pipeline-runs',
    face: 'django',
    kind: 'current',
    method: 'GET',
    path: '/api/pipeline-runs/',
    summary:
      'Every run the caller can see (bare array, newest first, unpaginated; superusers see every workspace).',
    responses: { 200: z.array(pipelineRunDTO) },
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
      'Paginated runs in the contract shape; omit workspace_id for every workspace the caller can see.',
    query: runsQuery,
    responses: { 200: runPage },
  },
  {
    id: 'pipeline-runs.overview.bff',
    resource: 'pipeline-runs',
    face: 'bff',
    kind: 'bff',
    method: 'GET',
    path: '/bff/pipeline-runs/overview',
    summary:
      'Runs across every workspace plus the workspaces themselves, in one payload for the Studio overview (newest 500 runs).',
    responses: { 200: runsOverview },
  },
  {
    id: 'pipeline-runs.edition.bff',
    resource: 'pipeline-runs',
    face: 'bff',
    kind: 'bff',
    method: 'GET',
    path: '/bff/pipeline-runs/{run_id}/edition',
    summary:
      'The edition a completed run produced (composed from its papers); 404 for runs that have none.',
    responses: { 200: edition },
    probe: { requires: ['run_id'] },
  },
]

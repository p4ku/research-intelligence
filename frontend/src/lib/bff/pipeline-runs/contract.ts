/** Pipeline-runs contract registry entries. Pure. */
import * as z from 'zod'
import type { Operation } from '../core/contract-types'
import { abortedRun, runPage, runsQuery, startedRun, startRun } from './schema'
import {
  abortRunResponseDTO,
  pipelineRunDetailDTO,
  pipelineRunDTO,
  startRunRequestDTO,
  startRunResponseDTO,
} from './upstream'

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
    id: 'pipeline-runs.start.current',
    resource: 'pipeline-runs',
    face: 'django',
    kind: 'current',
    method: 'POST',
    path: '/api/pipeline-runs/start/',
    summary:
      'Start an autonomous run for a workspace over a search window (start_date/end_date, YYYY-MM-DD); answers with a status envelope carrying pipeline_run_id. Never executed by the checker.',
    body: startRunRequestDTO,
    responses: { 201: startRunResponseDTO },
  },
  {
    id: 'pipeline-runs.abort.current',
    resource: 'pipeline-runs',
    face: 'django',
    kind: 'current',
    method: 'POST',
    path: '/api/pipeline-runs/{run_id}/abort/',
    summary:
      'Stop a run in flight: the run and its active steps become `aborted`. Refusals are 400 with an `error` sentence (already ended; caller not an admin or manager of the workspace); non-members get 404. Never executed by the checker.',
    responses: { 200: abortRunResponseDTO },
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
  {
    id: 'pipeline-runs.start.bff',
    resource: 'pipeline-runs',
    face: 'bff',
    kind: 'bff',
    method: 'POST',
    path: '/bff/pipeline-runs/start',
    summary:
      "Start a briefing run for one of the user's domains; the new run appears at the top of /bff/pipeline-runs as `running`.",
    body: startRun,
    responses: { 201: startedRun },
  },
  {
    id: 'pipeline-runs.abort.bff',
    resource: 'pipeline-runs',
    face: 'bff',
    kind: 'bff',
    method: 'POST',
    path: '/bff/pipeline-runs/{run_id}/abort',
    summary:
      'Stop a run in flight. 409 once it has already ended, 403 unless the caller is an admin or manager of its domain; the row reads `aborted` on the next /bff/pipeline-runs.',
    responses: { 200: abortedRun },
  },
]

/** Component-runs contract registry entries. Pure. */
import * as z from 'zod'
import type { Operation } from '../core/contract-types'
import { componentRunPage, componentRunsQuery } from './schema'
import { componentRunDTO } from './upstream'

export const componentRunsOperations: Operation[] = [
  {
    id: 'component-runs.list.current',
    resource: 'component-runs',
    face: 'django',
    kind: 'current',
    method: 'GET',
    path: '/api/component-runs/?pipeline_run={run_id}',
    summary: 'Steps of one run (bare array, newest first; ?step_type= and ?status= supported).',
    responses: { 200: z.array(componentRunDTO) },
    probe: { requires: ['run_id'] },
  },
  {
    id: 'component-runs.list.bff',
    resource: 'component-runs',
    face: 'bff',
    kind: 'bff',
    method: 'GET',
    path: '/bff/component-runs',
    summary: 'Steps of one run in execution order, metrics resolved per step type.',
    query: componentRunsQuery,
    responses: { 200: componentRunPage },
  },
]

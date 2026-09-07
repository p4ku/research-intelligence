/** Briefings contract registry entries. Pure. */
import type { Operation } from '../core/contract-types'
import { edition, editionPage, editionsQuery } from './schema'

export const briefingsOperations: Operation[] = [
  {
    id: 'briefings.list.desired',
    resource: 'briefings',
    face: 'django',
    kind: 'desired',
    method: 'GET',
    path: '/api/workspaces/{workspace_id}/editions/',
    summary:
      'One briefing edition per completed pipeline run, newest first, with model-written title/in_brief. Reference composition: src/lib/bff/briefings/service.ts; prose starting point: build_pipeline_run_digest_payload (tasks/auxiliary/email_digest.py).',
    query: editionsQuery.omit({ workspace_id: true }),
    responses: { 200: editionPage },
    probe: { requires: ['workspace_id'] },
  },
  {
    id: 'briefings.detail.desired',
    resource: 'briefings',
    face: 'django',
    kind: 'desired',
    method: 'GET',
    path: '/api/workspaces/{workspace_id}/editions/{date}/',
    summary: 'One edition (latest run of that day) including the screening exclusions.',
    responses: { 200: edition },
    probe: { requires: ['workspace_id', 'date'] },
  },
  {
    id: 'briefings.list.bff',
    resource: 'briefings',
    face: 'bff',
    kind: 'bff',
    method: 'GET',
    path: '/bff/briefings',
    summary:
      'Paginated edition summaries; ?workspace_id= narrows to one domain, otherwise every domain the user belongs to.',
    query: editionsQuery,
    responses: { 200: editionPage },
  },
  {
    id: 'briefings.detail.bff',
    resource: 'briefings',
    face: 'bff',
    kind: 'bff',
    method: 'GET',
    path: '/bff/briefings/{date}',
    summary:
      'One edition with exclusions; ?workspace_id= picks the domain, otherwise the newest edition of that day across domains.',
    responses: { 200: edition },
  },
]

/** Workspaces contract registry entries. Pure. */
import * as z from 'zod'
import type { Operation } from '../core/contract-types'
import { workspacePage, workspacesQuery } from './schema'
import { workspaceDTO } from './upstream'

export const workspacesOperations: Operation[] = [
  {
    id: 'workspaces.list.current',
    resource: 'workspaces',
    face: 'django',
    kind: 'current',
    method: 'GET',
    path: '/api/workspaces/',
    summary: "The user's workspaces (bare array) — the shape the BFF normalises today.",
    responses: { 200: z.array(workspaceDTO) },
  },
  {
    id: 'workspaces.list.desired',
    supersedes: 'workspaces.list.current',
    resource: 'workspaces',
    face: 'django',
    kind: 'desired',
    method: 'GET',
    path: '/api/workspaces/',
    summary:
      'Same endpoint, paginated ({count,next,previous,results}) with ?ordering=. Low priority.',
    query: workspacesQuery,
    responses: { 200: workspacePage },
  },
  {
    id: 'workspaces.list.bff',
    resource: 'workspaces',
    face: 'bff',
    kind: 'bff',
    method: 'GET',
    path: '/bff/workspaces',
    summary: "Paginated view of the user's workspaces in the contract shape.",
    query: workspacesQuery,
    responses: { 200: workspacePage },
  },
]

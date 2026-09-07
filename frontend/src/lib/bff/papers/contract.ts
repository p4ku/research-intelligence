/**
 * The papers contract registry entries: what the BFF depends on today
 * (`current`), the endpoints we are asking the backend team to build
 * (`desired`), and our own HTTP face (`bff`). Pure.
 */
import * as z from 'zod'
import type { Operation } from '../core/contract-types'
import { workspace } from '../workspaces/schema'
import {
  palette,
  paletteQuery,
  paperList,
  paperPage,
  papersQuery,
  papersScorecardQuery,
  scoredPaper,
} from './schema'
import { extractionDTO, paperDTO } from './upstream'

export const papersOperations: Operation[] = [
  {
    id: 'papers.list.current',
    resource: 'papers',
    face: 'django',
    kind: 'current',
    method: 'GET',
    path: '/api/papers/',
    summary:
      "Every paper across the user's workspaces (bare array, no filters) — what the composed source consumes.",
    responses: { 200: z.array(paperDTO) },
  },
  {
    id: 'papers.extractions.current',
    resource: 'papers',
    face: 'django',
    kind: 'current',
    method: 'GET',
    path: '/api/extractions/',
    summary: 'Every extraction (bare array) — dimension values are derived from fields_data.',
    responses: { 200: z.array(extractionDTO) },
  },
  {
    id: 'papers.list.desired',
    resource: 'papers',
    face: 'django',
    kind: 'desired',
    method: 'GET',
    path: '/api/workspaces/{workspace_id}/papers/',
    summary:
      'Workspace-scoped, paginated scorecard: papers with signal_score and resolved dimensions inline. Port reference: src/lib/papers/map.ts + src/lib/bff/papers/compose.ts.',
    query: papersScorecardQuery,
    responses: { 200: paperPage },
    probe: { requires: ['workspace_id'] },
  },
  {
    id: 'papers.detail.desired',
    resource: 'papers',
    face: 'django',
    kind: 'desired',
    method: 'GET',
    path: '/api/papers/{paper_id}/scorecard/',
    summary: 'One paper in the scorecard shape, with its workspace summary.',
    responses: { 200: z.object({ workspace, paper: scoredPaper }) },
    probe: { requires: ['paper_id'] },
  },
  {
    id: 'papers.list.bff',
    resource: 'papers',
    face: 'bff',
    kind: 'bff',
    method: 'GET',
    path: '/bff/papers',
    summary:
      "The Papers page, one page at a time: screening, ordering, search, starred, minimum score, TRL window and ingested window over every domain the user belongs to (?workspace_id= narrows to one), with the rail's corpus-wide facets alongside.",
    query: papersQuery,
    responses: { 200: paperList },
  },
  {
    id: 'papers.detail.bff',
    resource: 'papers',
    face: 'bff',
    kind: 'bff',
    method: 'GET',
    path: '/bff/papers/{paper_id}',
    summary: 'One paper with its workspace summary.',
    responses: { 200: z.object({ workspace, paper: scoredPaper }) },
  },
  {
    id: 'papers.palette.bff',
    resource: 'papers',
    face: 'bff',
    kind: 'bff',
    method: 'GET',
    path: '/bff/papers/palette',
    summary:
      "The Ask picker's rows: the papers `q` matches (the shared matcher; empty = best signal first), at most `limit`, as slim rows (title, first author, source, signal) with the matched and total counts. Served from a short per-user cache.",
    query: paletteQuery,
    responses: { 200: palette },
  },
]

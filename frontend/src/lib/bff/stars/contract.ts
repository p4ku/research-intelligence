/** Stars contract registry entries: the endpoint we are asking for, and our own face. Pure. */
import type { Operation } from '../core/contract-types'
import { stars, starUpdate } from './schema'

export const starsOperations: Operation[] = [
  {
    id: 'stars.get.desired',
    resource: 'stars',
    face: 'django',
    kind: 'desired',
    method: 'GET',
    path: '/api/stars/',
    summary:
      "The calling user's starred paper ids and briefing (pipeline-run) ids. Backend mapping suggestion: one Star row per (user, kind, id).",
    responses: { 200: stars },
  },
  {
    id: 'stars.set.desired',
    resource: 'stars',
    face: 'django',
    kind: 'desired',
    method: 'PUT',
    path: '/api/stars/',
    summary: 'Star or unstar one record for the calling user; responds with the full set.',
    body: starUpdate,
    responses: { 200: stars },
  },
  {
    id: 'stars.get.bff',
    resource: 'stars',
    face: 'bff',
    kind: 'bff',
    method: 'GET',
    path: '/bff/stars',
    summary: "The user's stars. Cookie-backed stub until Django persists them.",
    responses: { 200: stars },
  },
  {
    id: 'stars.set.bff',
    resource: 'stars',
    face: 'bff',
    kind: 'bff',
    method: 'PUT',
    path: '/bff/stars',
    summary: 'Star or unstar a paper or briefing; responds with the full set.',
    body: starUpdate,
    responses: { 200: stars },
  },
]

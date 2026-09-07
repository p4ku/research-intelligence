/** The search contract registry entry: our own HTTP face only — nothing new is asked of Django. Pure. */
import type { Operation } from '../core/contract-types'
import { searchQuery, searchResponse } from './schema'

export const searchOperations: Operation[] = [
  {
    id: 'search.bff',
    resource: 'search',
    face: 'bff',
    kind: 'bff',
    method: 'GET',
    path: '/bff/search',
    summary:
      'Typeahead over every paper the user can see: ranked hits, matching domains, an Ask action scoped to the top hit; an arXiv id or DOI resolves to one paper.',
    query: searchQuery,
    responses: { 200: searchResponse },
  },
]

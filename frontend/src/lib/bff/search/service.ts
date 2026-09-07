/**
 * Search service — the seam the route goes through. Composed only: it
 * follows whatever sources papers, workspaces and briefings are on. Server-only.
 */
import 'server-only'

import { assembleSearch } from './assemble'
import { searchCorpus } from './corpus'
import type { SearchQuery, SearchResponse } from './schema'

export const search = {
  async run(query: SearchQuery): Promise<SearchResponse> {
    return assembleSearch(await searchCorpus(), query)
  },
}

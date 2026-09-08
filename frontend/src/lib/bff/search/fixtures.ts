/**
 * The search response for `q=agents` over the paper fixtures — the OpenAPI
 * example, and what the contract test parses. Derived, not hand-written,
 * so it cannot drift from the assembler. Pure.
 */
import { fixtureEditions } from '../briefings/fixtures'
import { fixturePapers, fixtureWorkspace } from '../papers/fixtures'
import { assembleSearch, type SearchCorpus } from './assemble'
import type { SearchResponse } from './schema'

export const fixtureSearchCorpus: SearchCorpus = {
  workspaces: [fixtureWorkspace],
  papers: fixturePapers,
  latestEdition: {
    [fixtureWorkspace.id]: fixtureEditions[0]
      ? { date: fixtureEditions[0].date, runId: fixtureEditions[0].run_id }
      : null,
  },
}

export const fixtureSearchResponse: SearchResponse = assembleSearch(fixtureSearchCorpus, {
  q: 'agents',
  limit: 8,
})

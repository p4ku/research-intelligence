/**
 * The corpus the typeahead searches: every paper the user can see (the same
 * corpus the Ask picker reads) plus each domain's newest edition date.
 * Everything here derives from the corpus snapshot, which is held across
 * requests, so assembling it per request is cheap.
 *
 * Server-only.
 */
import 'server-only'

import { briefings } from '../briefings/service'
import { papers } from '../papers/service'
import type { SearchCorpus } from './assemble'

/** The user's search corpus. */
export async function searchCorpus(): Promise<SearchCorpus> {
  const { workspaces, papers: all } = await papers.listEverywhere()
  const latest = await Promise.all(
    workspaces.map(async (ws): Promise<[string, string | null]> => {
      const editions = await briefings.listAll(ws.id, 'en')
      return [ws.id, editions[0]?.date ?? null]
    }),
  )
  return { workspaces, papers: all, latestEdition: Object.fromEntries(latest) }
}

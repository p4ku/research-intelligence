/**
 * The corpus the typeahead searches: every paper the user can see (the same
 * corpus the Ask picker reads) plus each domain's newest edition.
 * Everything here derives from the corpus snapshot, which is held across
 * requests, so assembling it per request is cheap.
 *
 * Server-only.
 */
import 'server-only'

import { briefings } from '../briefings/service'
import { papers } from '../papers/service'
import type { LatestEdition, SearchCorpus } from './assemble'

/** The user's search corpus. */
export async function searchCorpus(): Promise<SearchCorpus> {
  const { workspaces, papers: all } = await papers.listEverywhere()
  const latest = await Promise.all(
    workspaces.map(async (ws): Promise<[string, LatestEdition | null]> => {
      const [newest] = await briefings.listAll(ws.id, 'en')
      return [ws.id, newest ? { date: newest.date, runId: newest.run_id } : null]
    }),
  )
  return { workspaces, papers: all, latestEdition: Object.fromEntries(latest) }
}

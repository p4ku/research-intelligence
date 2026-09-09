/**
 * The `composed` source for papers: assembles `ScoredPaper` from the three
 * unfiltered, unpaginated endpoints Django offers today (papers, extractions,
 * workspaces), exactly the logic we are asking the backend to absorb into a
 * scorecard endpoint. The pure derivation rules live in src/lib/papers/map.ts
 * — that file (with map.test.ts as acceptance cases) is the port reference.
 * Server-only.
 */
import 'server-only'

import { cache } from 'react'
import { corpusSnapshot } from '../corpus/snapshot'

// The lists come from the user's corpus snapshot (../corpus/snapshot.ts),
// held across requests; single-paper scorecards come directly from the dedicated
// /api/papers/{id}/scorecard/ endpoint in service.ts.
// Retained purely for snapshot-backed raw list compatibility.
export const listPapersRaw = cache(async () => (await corpusSnapshot()).papers)
export const listExtractionsRaw = cache(async () => (await corpusSnapshot()).extractions)

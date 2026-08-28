/** Contract-shaped edition fixtures for the `stub` source and spec examples. Pure. */
import { fixturePapers, fixtureWorkspace } from '../papers/fixtures'
import type { Edition } from './schema'

const surfaced = fixturePapers[0]
const excluded = fixturePapers[1]

export const fixtureEditions: Edition[] = [
  {
    run_id: '00000000-0000-4000-8000-000000000031',
    workspace_id: fixtureWorkspace.id,
    date: '2026-08-27',
    title: 'Coordinated Tool Use in Multi-Agent Language Model Systems',
    in_brief:
      'The Agentic AI scan fetched 12 papers, passed 5 through screening, and surfaced 1 for this briefing. Leading the list: “Coordinated Tool Use in Multi-Agent Language Model Systems” at signal 88.',
    in_brief_source: 'template',
    funnel: { fetched: 12, passed_screening: 5, surfaced: 1 },
    papers: [
      {
        id: surfaced.id,
        title: surfaced.title,
        authors: surfaced.authors,
        source: surfaced.source,
        signal_score: surfaced.signal_score,
      },
    ],
    exclusions: [
      {
        paper_id: excluded.id,
        title: excluded.title,
        source: excluded.source,
        reason: excluded.screening_reasoning,
      },
    ],
    generated_at: '2026-08-27T06:20:00Z',
  },
]

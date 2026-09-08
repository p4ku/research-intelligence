/** Contract-shaped edition fixtures for the `stub` source and spec examples. Pure. */
import { FIXTURE_RERUN, FIXTURE_RUN, fixturePapers, fixtureWorkspace } from '../papers/fixtures'
import type { Edition } from './schema'

const surfaced = fixturePapers[0]!
const excluded = fixturePapers[1]!

/**
 * Two editions of one day in one domain — the morning run and its noon
 * rerun (../pipeline-runs/fixtures.ts), so the stub source, the gallery
 * and the tests all hold a same-day pair. Dates and stamps are the runs'
 * completion, as the composed source addresses them. Home and the archive
 * join editions to runs by `run_id`.
 */
export const fixtureEditions: Edition[] = [
  {
    run_id: FIXTURE_RERUN,
    workspace_id: fixtureWorkspace.id,
    date: '2026-08-31',
    title: 'Coordinated Tool Use in Multi-Agent Language Model Systems',
    in_brief:
      'The Agentic AI scan fetched 4 papers, passed 1 through screening, and surfaced 1 for this briefing. Leading the list: “Coordinated Tool Use in Multi-Agent Language Model Systems” at signal 84.',
    in_brief_source: 'template',
    funnel: { fetched: 4, passed_screening: 1, surfaced: 1 },
    papers: [
      {
        id: surfaced.id,
        title: surfaced.title,
        authors: surfaced.authors,
        source: surfaced.source,
        screening_status: surfaced.screening_status,
        // Rescored by the rerun; the morning edition below keeps its 87.5.
        signal_score: 84,
      },
    ],
    exclusions: [],
    generated_at: '2026-08-31T12:03:00.000000Z',
  },
  {
    run_id: FIXTURE_RUN,
    workspace_id: fixtureWorkspace.id,
    date: '2026-08-31',
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
        screening_status: surfaced.screening_status,
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
    generated_at: '2026-08-31T08:29:05.470057Z',
  },
]

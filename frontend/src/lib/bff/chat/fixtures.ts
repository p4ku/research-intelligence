/**
 * Contract-shaped chat fixtures for the `stub` source (offline UI work) and
 * the OpenAPI examples. Pure; validated by src/lib/bff/fixtures.test.ts.
 */
import { fixturePapers, fixtureWorkspace } from '../papers/fixtures'
import type { ChatEvent, ChatSession, ChatSessionDetail } from './schema'

const PAPER = fixturePapers[0]

export const fixtureSessions: ChatSession[] = [
  {
    id: '00000000-0000-4000-8000-000000000051',
    workspace_id: fixtureWorkspace.id,
    paper_id: PAPER.id,
    paper_title: PAPER.title,
    title: 'What does this paper enable?',
    summary: null,
    turns_count: 2,
    created_at: '2026-08-27T09:12:00Z',
    updated_at: '2026-08-27T09:14:06Z',
  },
  {
    id: '00000000-0000-4000-8000-000000000052',
    workspace_id: fixtureWorkspace.id,
    paper_id: null,
    paper_title: null,
    title: 'Which papers moved the most this week?',
    summary: null,
    turns_count: 1,
    created_at: '2026-08-26T16:40:00Z',
    updated_at: '2026-08-26T16:40:30Z',
  },
]

export const fixtureSessionDetails: ChatSessionDetail[] = [
  {
    ...fixtureSessions[0],
    turns: [
      {
        id: '00000000-0000-4000-8000-000000000061',
        question: 'What does this paper enable?',
        // The model's inline marker stays in the stored answer (the backend
        // parses it into `visual_citations` but does not strip it).
        answer:
          'It shows cooperating language-model agents can divide tool use adaptively [Page 7, Figure 4b, box_2d: [320, 150, 680, 890], quote: "agents divide tool use adaptively"], lifting task completion by 31% over a single-agent baseline on the new benchmark.',
        status: 'completed',
        deep_thinking: false,
        visual_citations: [
          {
            page: 7,
            label: 'Figure 4b',
            box_2d: [320, 150, 680, 890],
            quote: 'agents divide tool use adaptively',
            verified_in_source: true,
          },
        ],
        fact_check: {
          verified: true,
          grounding_score: 1,
          verified_count: 1,
          total_count: 1,
          status: 'PASS',
        },
        usage: { tokens_in: 4200, tokens_out: 260, total_tokens: 4460, usd_cost: 0.0042 },
        error: null,
        created_at: '2026-08-27T09:12:00Z',
        completed_at: '2026-08-27T09:12:40Z',
      },
      {
        // The reader pressed Stop: the words that had arrived are the answer.
        id: '00000000-0000-4000-8000-000000000062',
        question: 'And the cost of that coordination?',
        answer:
          'Coordination adds roughly one extra model call per hand-off, which the paper prices at',
        status: 'aborted',
        deep_thinking: false,
        visual_citations: [],
        fact_check: null,
        usage: { tokens_in: 4300, tokens_out: 18, total_tokens: 4318, usd_cost: 0.0033 },
        error: null,
        created_at: '2026-08-27T09:14:00Z',
        completed_at: '2026-08-27T09:14:06Z',
      },
    ],
  },
  { ...fixtureSessions[1], turns: [] },
]

/** A full stub stream, replayed with small delays by the stream route. */
export const fixtureStreamFrames: ChatEvent[] = [
  {
    event: 'metadata',
    data: {
      message_id: '00000000-0000-4000-8000-000000000071',
      session_id: fixtureSessions[0].id,
      scope: { workspace_id: fixtureWorkspace.id, paper_id: PAPER.id },
    },
  },
  {
    event: 'citations',
    data: {
      items: [
        {
          paper_id: PAPER.id,
          title: PAPER.title,
          signal_score: PAPER.signal_score,
          href: `/papers/${PAPER.id}`,
        },
      ],
    },
  },
  // A citation marker split across frames, as Django's raw deltas do it.
  { event: 'delta', data: { text: 'The paper demonstrates that cooperating agents ' } },
  {
    event: 'delta',
    data: { text: 'divide tool use adaptively [Page 7, Figure 4b, box_2d: [320, 150, ' },
  },
  {
    event: 'delta',
    data: {
      text: '680, 890], quote: "agents divide tool use adaptively"], lifting task completion by 31% over a single-agent baseline.',
    },
  },
  {
    event: 'visual_citations',
    data: {
      items: [
        {
          page: 7,
          label: 'Figure 4b',
          box_2d: [320, 150, 680, 890],
          quote: 'agents divide tool use adaptively',
          verified_in_source: true,
        },
      ],
    },
  },
  {
    event: 'fact_check',
    data: { verified: true, grounding_score: 1, verified_count: 1, total_count: 1, status: 'PASS' },
  },
  {
    event: 'usage',
    data: { tokens_in: 4200, tokens_out: 260, total_tokens: 4460, usd_cost: 0.0042 },
  },
  {
    event: 'done',
    data: {
      message_id: '00000000-0000-4000-8000-000000000071',
      session_id: fixtureSessions[0].id,
    },
  },
]

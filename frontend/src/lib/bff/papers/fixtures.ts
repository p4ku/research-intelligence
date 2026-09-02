/**
 * Contract-shaped fixtures for the `stub` source and for the OpenAPI
 * examples. Deterministic fake UUIDs; validated against the schemas by
 * src/lib/bff/fixtures.test.ts. Pure.
 */
import type { WorkspaceSummary } from '../workspaces/schema'
import type { ScoredPaper } from './schema'

export const fixtureWorkspace: WorkspaceSummary = {
  id: '00000000-0000-4000-8000-000000000001',
  name: 'Agentic AI Scan (fixture)',
  user_role: 'researcher',
  definitions: [
    {
      id: '00000000-0000-4000-8000-000000000011',
      name: 'Fit Score',
      key: 'fit_score',
      is_active: true,
      is_trl: false,
      max: 100,
    },
    {
      id: '00000000-0000-4000-8000-000000000012',
      name: 'Novelty Score',
      key: 'novelty_score',
      is_active: true,
      is_trl: false,
      max: 10,
    },
    {
      id: '00000000-0000-4000-8000-000000000013',
      name: 'TRL Level',
      key: 'trl_level',
      is_active: true,
      is_trl: true,
      max: 9,
    },
  ],
  scrapers: [
    {
      id: '00000000-0000-4000-8000-000000000021',
      provider: 'arxiv',
      search_query: 'agentic AI OR multi-agent systems',
      is_active: true,
    },
  ],
  digest_schedule: '0 7 * * *',
  screening_llm_model: 'google/gemini-3.7-flash',
  llm_provider: 'google',
  created_at: '2026-08-01T06:00:00Z',
}

const RUN_ID = '00000000-0000-4000-8000-000000000031'

export const fixturePapers: ScoredPaper[] = [
  {
    id: '00000000-0000-4000-8000-000000000041',
    workspace_id: fixtureWorkspace.id,
    pipeline_run_id: RUN_ID,
    title: 'Coordinated Tool Use in Multi-Agent Language Model Systems',
    authors: ['A. Example', 'B. Beispiel'],
    authors_raw: 'A. Example, B. Beispiel',
    abstract:
      'We study how cooperating language-model agents divide tool use and show a 31% task-completion gain over single-agent baselines on a new benchmark.',
    doi: null,
    arxiv_id: '2608.01234',
    source: 'arxiv',
    screening_status: 'full_text_passed',
    screening_reasoning:
      'Directly on-topic: multi-agent coordination with an empirical evaluation.',
    signal_score: 87.5,
    signal_score_details: {
      variables: { fit_score: 92, novelty_score: 8, trl_level: 4 },
      code_snippet: 'signal_score = fit_score * 0.7 + novelty_score * 10 * 0.3',
      calculated_at: '2026-08-27T06:15:00Z',
      error: null,
    },
    dimensions: [
      {
        key: 'fit_score',
        definition_id: fixtureWorkspace.definitions[0].id,
        name: 'Fit Score',
        value: 92,
        raw: '92',
        max: 100,
        is_trl: false,
        rationale: 'Squarely in the agentic-AI focus.',
        evidence: ['“agents divide tool use adaptively”'],
        confidence: 0.86,
      },
      {
        key: 'novelty_score',
        definition_id: fixtureWorkspace.definitions[1].id,
        name: 'Novelty Score',
        value: 8,
        raw: '8',
        max: 10,
        is_trl: false,
      },
      {
        key: 'trl_level',
        definition_id: fixtureWorkspace.definitions[2].id,
        name: 'TRL Level',
        value: 4,
        raw: 'TRL 4',
        max: 9,
        is_trl: true,
      },
    ],
    pdf_key: null,
    markdown_key: null,
    pdf_url: 'https://arxiv.org/pdf/2608.01234.pdf',
    is_benchmark: false,
    evaluation_label: null,
    created_at: '2026-08-27T05:58:00Z',
  },
  {
    id: '00000000-0000-4000-8000-000000000042',
    workspace_id: fixtureWorkspace.id,
    pipeline_run_id: RUN_ID,
    title: 'A Survey of Evaluation Protocols for Autonomous Web Agents',
    authors: ['C. Author'],
    authors_raw: 'C. Author',
    abstract: 'A survey of evaluation protocols; no new system is proposed.',
    doi: '10.1000/fixture.42',
    arxiv_id: null,
    source: 'openalex',
    screening_status: 'rejected',
    screening_reasoning: 'Survey without an empirical contribution; excluded by criteria.',
    signal_score: null,
    signal_score_details: null,
    dimensions: [],
    pdf_key: null,
    markdown_key: null,
    pdf_url: 'https://doi.org/10.1000/fixture.42',
    is_benchmark: false,
    evaluation_label: null,
    created_at: '2026-08-27T05:59:00Z',
  },
]

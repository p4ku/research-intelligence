/**
 * Contract-shaped fixtures for the `stub` source and for the OpenAPI
 * examples. Deterministic fake UUIDs; validated against the schemas by
 * src/lib/bff/fixtures.test.ts. Pure.
 */
import type * as z from 'zod'
import type { WorkspaceSummary } from '../workspaces/schema'
import type { ScoredPaper } from './schema'
import type { paperDTO, paperMetricDTO } from './upstream'

type PaperDTO = z.infer<typeof paperDTO>
type PaperMetricDTO = z.infer<typeof paperMetricDTO>

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
  screening_llm_model: 'google/gemini-3.8-flash',
  llm_provider: 'google',
  created_at: '2026-08-01T06:00:00Z',
}

/** The fixture runs (../pipeline-runs/fixtures.ts): the morning briefing and the same-day rerun. */
export const FIXTURE_RUN = '00000000-0000-4000-8000-000000000101'
export const FIXTURE_RERUN = '00000000-0000-4000-8000-000000000104'

/**
 * The scored corpus as the morning run left it: two papers, one accepted at
 * 87.5 with its dimensions, one rejected. `fixturePaperDTOs` below is the
 * same two papers after the noon rerun, as Django's serializer sends them.
 */
export const fixturePapers: ScoredPaper[] = [
  {
    id: '00000000-0000-4000-8000-000000000041',
    workspace_id: fixtureWorkspace.id,
    pipeline_run_id: FIXTURE_RUN,
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
    abstract_screening_reasoning:
      'The abstract proposes a coordination protocol for cooperating language-model agents and reports an empirical gain, matching the acceptance criteria.',
    full_text_screening_reasoning:
      'The full text carries a complete method, a new benchmark with three suites, and an ablation over the number of agents; directly on-topic for the workspace.',
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
        band: 'Strong',
        facets: [
          {
            key: 'need_match_score',
            name: 'Need match',
            value: 94,
            max: 100,
            text: 'Coordinated tool use is the question the workspace scans for; the protocol applies directly to the assistant fleet.',
          },
          { key: 'adoption_route_score', name: 'Adoption route', value: 88, max: 100, text: null },
        ],
        lists: [
          {
            key: 'key_contributions',
            name: 'Key contributions',
            items: [
              'A shared scratchpad and arbitration protocol for cooperating agents.',
              'A three-suite benchmark for redundant tool calls.',
            ],
          },
        ],
        facts: [{ key: 'limitations_acknowledged', name: 'Limitations acknowledged', value: true }],
        model: 'google/gemini-3.8-flash',
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
    source_url: 'https://arxiv.org/abs/2608.01234',
    is_benchmark: false,
    evaluation_label: null,
    published_date: '2026-08-19',
    created_at: '2026-08-27T05:58:00Z',
    pipeline_run_name: 'Scheduled Run - Agentic AI 2AM',
  },
  {
    id: '00000000-0000-4000-8000-000000000042',
    workspace_id: fixtureWorkspace.id,
    pipeline_run_id: FIXTURE_RUN,
    title: 'A Survey of Evaluation Protocols for Autonomous Web Agents',
    authors: ['C. Author'],
    authors_raw: 'C. Author',
    abstract: 'A survey of evaluation protocols; no new system is proposed.',
    doi: '10.1000/fixture.42',
    arxiv_id: null,
    source: 'openalex',
    screening_status: 'rejected',
    screening_reasoning: 'Survey without an empirical contribution; excluded by criteria.',
    abstract_screening_reasoning: null,
    full_text_screening_reasoning: null,
    signal_score: null,
    signal_score_details: null,
    dimensions: [],
    pdf_key: null,
    markdown_key: null,
    source_url: 'https://doi.org/10.1000/fixture.42',
    is_benchmark: false,
    evaluation_label: null,
    published_date: null,
    created_at: '2026-08-27T05:59:00Z',
    pipeline_run_name: null,
  },
]

const RERUN_REASON =
  'Rerun: still squarely on topic; the benchmark has since been superseded, so the score is revised.'

function metricRow(
  paper: string,
  pipeline_run: string,
  n: number,
  row: Partial<PaperMetricDTO>,
): PaperMetricDTO {
  return {
    id: `00000000-0000-4000-8000-0000000005${String(n).padStart(2, '0')}`,
    paper,
    pipeline_run,
    workspace: fixtureWorkspace.id,
    signal_score: null,
    signal_score_details: {},
    metrics_data: { fit_score: 0, novelty_score: 0, trl_level: 0 },
    created_at: '2026-08-31T08:28:00Z',
    ...row,
  }
}

/**
 * The same two papers after the noon rerun, as Django's paper serializer
 * sends them — the shape `indexRuns` and the composed source read. The
 * first paper was scored in both fixture runs, with one metric row per run:
 * 87.5 in the morning (the row `fixturePapers` shows), rescored to 84 by the
 * rerun, and the paper-level fields collapsed to the rerun (the workspace's
 * latest run), as the serializer collapses them. The second was seen by the
 * morning run only.
 */
export const fixturePaperDTOs: PaperDTO[] = [
  {
    id: fixturePapers[0]!.id,
    workspace: fixtureWorkspace.id,
    pipeline_run: FIXTURE_RERUN,
    hash_id: 'f1x7ur3-0000-0041',
    doi: null,
    arxiv_id: '2608.01234',
    title: fixturePapers[0]!.title,
    authors: fixturePapers[0]!.authors_raw,
    abstract: fixturePapers[0]!.abstract,
    source_database: 'arxiv',
    original_pdf_path: null,
    converted_md_path: null,
    source_url: fixturePapers[0]!.source_url,
    screening_status: 'full_text_passed',
    screening_reasoning: RERUN_REASON,
    abstract_screening_reasoning: null,
    full_text_screening_reasoning: RERUN_REASON,
    published_date: '2026-08-19',
    pipeline_run_name: null,
    is_evaluation_benchmark: false,
    evaluation_label: null,
    signal_score: 84,
    signal_score_details: {},
    metrics: [
      metricRow(fixturePapers[0]!.id, FIXTURE_RERUN, 2, {
        signal_score: 84,
        signal_score_details: {
          variables: { fit_score: 88, novelty_score: 7.5, trl_level: 4 },
          code_snippet: 'signal_score = fit_score * 0.7 + novelty_score * 10 * 0.3',
          calculated_at: '2026-08-31T12:02:30Z',
          error: null,
        },
        metrics_data: { fit_score: 88, novelty_score: 7.5, trl_level: 4 },
        screening_status: 'full_text_passed',
        full_text_screening_reasoning: RERUN_REASON,
        created_at: '2026-08-31T12:02:00Z',
      }),
      metricRow(fixturePapers[0]!.id, FIXTURE_RUN, 1, {
        signal_score: 87.5,
        signal_score_details: {
          variables: { fit_score: 92, novelty_score: 8, trl_level: 4 },
          code_snippet: 'signal_score = fit_score * 0.7 + novelty_score * 10 * 0.3',
          calculated_at: '2026-08-31T08:28:30Z',
          error: null,
        },
        metrics_data: { fit_score: 92, novelty_score: 8, trl_level: 4 },
        screening_status: 'full_text_passed',
        abstract_screening_reasoning: fixturePapers[0]!.abstract_screening_reasoning,
        full_text_screening_reasoning: fixturePapers[0]!.full_text_screening_reasoning,
      }),
    ],
    created_at: '2026-08-27T05:58:00Z',
  },
  {
    id: fixturePapers[1]!.id,
    workspace: fixtureWorkspace.id,
    pipeline_run: FIXTURE_RUN,
    hash_id: 'f1x7ur3-0000-0042',
    doi: '10.1000/fixture.42',
    arxiv_id: null,
    title: fixturePapers[1]!.title,
    authors: fixturePapers[1]!.authors_raw,
    abstract: fixturePapers[1]!.abstract,
    source_database: 'openalex',
    original_pdf_path: null,
    converted_md_path: null,
    source_url: fixturePapers[1]!.source_url,
    screening_status: 'rejected',
    screening_reasoning: fixturePapers[1]!.screening_reasoning,
    abstract_screening_reasoning: fixturePapers[1]!.screening_reasoning,
    full_text_screening_reasoning: null,
    published_date: null,
    pipeline_run_name: null,
    is_evaluation_benchmark: false,
    evaluation_label: null,
    signal_score: null,
    signal_score_details: {},
    metrics: [
      metricRow(fixturePapers[1]!.id, FIXTURE_RUN, 3, {
        screening_status: 'rejected',
        abstract_screening_reasoning: fixturePapers[1]!.screening_reasoning,
      }),
    ],
    created_at: '2026-08-27T05:59:00Z',
  },
]

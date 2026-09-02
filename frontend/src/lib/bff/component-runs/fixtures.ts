/**
 * Contract-shaped component-run fixtures: the six steps of a typical run, in
 * the order the engine runs them, shaped like the 2026-09-01 production
 * snapshot rows that normalise.test.ts is built from. Spend and model are
 * recorded on the LLM steps only, as in production; the step-timeline
 * skeleton mirrors exactly that pattern, so this fixture is its drift
 * contract. Labels are what `labelFor` resolves for each component. Pure.
 */
import { fixtureOverviewRuns, fixtureRuns } from '../pipeline-runs/fixtures'
import type { ComponentCost, ComponentRun } from './schema'

const RUN_ID = fixtureRuns[0].id
const FAILED_RUN_ID = fixtureOverviewRuns[5].id

const unmeasured: ComponentCost = {
  usd: null,
  tokens_in: null,
  tokens_out: null,
  total_tokens: null,
  model: null,
}

export const fixtureSteps: ComponentRun[] = [
  {
    id: '00000000-0000-4000-8000-000000000201',
    pipeline_run_id: RUN_ID,
    step_type: 'search',
    component_name: 'arxiv_scraper',
    label: 'arXiv search',
    status: 'completed',
    summary: { kind: 'search', created: 10, fetched: 12, duplicates: 2 },
    cost: unmeasured,
    duration_seconds: 4.21,
    started_at: '2026-08-31T08:26:21.500000Z',
    completed_at: '2026-08-31T08:26:25.710000Z',
    error_message: null,
    storage_path: null,
  },
  {
    id: '00000000-0000-4000-8000-000000000202',
    pipeline_run_id: RUN_ID,
    step_type: 'download',
    component_name: 'document_download',
    label: 'Download',
    status: 'completed',
    summary: { kind: 'download', downloaded: 10, cached: 0, failed: 0 },
    cost: unmeasured,
    duration_seconds: 18.6,
    started_at: '2026-08-31T08:26:25.800000Z',
    completed_at: '2026-08-31T08:26:44.400000Z',
    error_message: null,
    storage_path: null,
  },
  {
    id: '00000000-0000-4000-8000-000000000203',
    pipeline_run_id: RUN_ID,
    step_type: 'ocr',
    component_name: 'layout_ocr',
    label: 'Layout OCR',
    status: 'skipped',
    summary: { kind: 'none' },
    cost: unmeasured,
    duration_seconds: 0,
    started_at: '2026-08-31T08:26:44.500000Z',
    completed_at: '2026-08-31T08:26:44.500000Z',
    error_message: null,
    storage_path: null,
  },
  {
    id: '00000000-0000-4000-8000-000000000204',
    pipeline_run_id: RUN_ID,
    step_type: 'screening',
    component_name: 'abstract_screening',
    label: 'Abstract screening',
    status: 'completed',
    summary: { kind: 'screening', screened: 10, passed: 9, rejected: 1, withdrawn: 0 },
    cost: {
      usd: 0.0412,
      tokens_in: 48210,
      tokens_out: 3120,
      total_tokens: 51330,
      model: 'google/gemini-3.7-flash',
    },
    duration_seconds: 31.9,
    started_at: '2026-08-31T08:26:44.600000Z',
    completed_at: '2026-08-31T08:27:16.500000Z',
    error_message: null,
    storage_path: null,
  },
  {
    id: '00000000-0000-4000-8000-000000000205',
    pipeline_run_id: RUN_ID,
    step_type: 'extraction',
    component_name: 'parameter_extraction',
    label: 'Parameter extraction',
    status: 'completed',
    summary: { kind: 'extraction', created: 45, papers: 9, definitions: 5, failed: 0 },
    cost: {
      usd: 0.6803,
      tokens_in: 812400,
      tokens_out: 20950,
      total_tokens: 833350,
      model: 'google/gemini-3.7-flash',
    },
    duration_seconds: 96.3,
    started_at: '2026-08-31T08:27:16.600000Z',
    completed_at: '2026-08-31T08:28:52.900000Z',
    error_message: null,
    storage_path: null,
  },
  {
    id: '00000000-0000-4000-8000-000000000206',
    pipeline_run_id: RUN_ID,
    step_type: 'signal_score',
    component_name: 'signal_score_evaluation',
    label: 'Signal score',
    status: 'completed',
    summary: { kind: 'signal_score', scored: 9, total: 9, avg: 61.4, max: 88.2 },
    cost: {
      usd: 0.0316,
      tokens_in: 18784,
      tokens_out: 874,
      total_tokens: 19658,
      model: 'google/gemini-3.7-flash',
    },
    duration_seconds: 12.6,
    started_at: '2026-08-31T08:28:53.000000Z',
    completed_at: '2026-08-31T08:29:05.600000Z',
    error_message: null,
    storage_path: null,
  },
]

/**
 * The steps of the overview fixture's failed run: search and download ran,
 * download failed with the message the run carries. The Studio overview's
 * detail pane marks the failed stage from this row, never from the run's
 * `current_stage`.
 */
export const fixtureStepsFailed: ComponentRun[] = [
  {
    id: '00000000-0000-4000-8000-000000000211',
    pipeline_run_id: FAILED_RUN_ID,
    step_type: 'search',
    component_name: 'arxiv_scraper',
    label: 'arXiv search',
    status: 'completed',
    summary: { kind: 'search', created: 41, fetched: 41, duplicates: 0 },
    cost: unmeasured,
    duration_seconds: 29,
    started_at: '2026-09-01T07:30:14.000000Z',
    completed_at: '2026-09-01T07:30:43.000000Z',
    error_message: null,
    storage_path: null,
  },
  {
    id: '00000000-0000-4000-8000-000000000212',
    pipeline_run_id: FAILED_RUN_ID,
    step_type: 'download',
    component_name: 'document_download',
    label: 'Download',
    status: 'failed',
    summary: { kind: 'download', downloaded: 15, cached: 0, failed: 7 },
    cost: unmeasured,
    duration_seconds: 524,
    started_at: '2026-09-01T07:32:24.000000Z',
    completed_at: '2026-09-01T07:41:08.000000Z',
    error_message:
      'HTTP 429 Too Many Requests from export.arxiv.org for 7 of 22 PDFs after 3 retries; step halted by operator',
    storage_path: null,
  },
]

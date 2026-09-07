/**
 * Contract-shaped pipeline-run fixtures for the skeleton gallery and tests.
 * Deterministic fake UUIDs; validated against the schemas by
 * src/lib/bff/fixtures.test.ts. Values follow what Django actually sends (the
 * local-data snapshots), not invented shapes. Pure.
 */
import { fixtureWorkspace } from '../papers/fixtures'
import type { PipelineRun, PipelineRunDetail } from './schema'

export const fixtureRuns: PipelineRun[] = [
  {
    id: '00000000-0000-4000-8000-000000000101',
    workspace_id: fixtureWorkspace.id,
    workspace_name: fixtureWorkspace.name,
    run_date: '2026-08-31',
    status: 'completed',
    current_stage: 'completed',
    total_papers_fetched: 10,
    total_papers_passed_screening: 9,
    status_message:
      'Full SLR pipeline finished successfully. Papers: 10 fetched, 9 passed screening, 45 parameter extractions completed.',
    duration_seconds: 164.052377,
    usd_cost: 0.7531,
    started_at: '2026-08-31T08:26:21.417680Z',
    completed_at: '2026-08-31T08:29:05.470057Z',
    period_start: '2026-08-01',
    period_end: '2026-08-31',
    lookback_days: null,
  },
  {
    id: '00000000-0000-4000-8000-000000000102',
    workspace_id: fixtureWorkspace.id,
    workspace_name: fixtureWorkspace.name,
    run_date: '2026-08-30',
    status: 'failed',
    current_stage: 'extraction',
    total_papers_fetched: 12,
    total_papers_passed_screening: 7,
    status_message: 'Parameter extraction failed: upstream model returned an empty response.',
    duration_seconds: 97.4,
    usd_cost: 0.3128,
    started_at: '2026-08-30T08:26:03.000000Z',
    completed_at: '2026-08-30T08:27:40.400000Z',
    period_start: '2026-08-01',
    period_end: '2026-08-30',
    lookback_days: null,
  },
  {
    id: '00000000-0000-4000-8000-000000000103',
    workspace_id: fixtureWorkspace.id,
    workspace_name: fixtureWorkspace.name,
    run_date: '2026-09-01',
    status: 'running',
    current_stage: 'abstract_screening',
    total_papers_fetched: 8,
    total_papers_passed_screening: 0,
    status_message: 'Screening abstracts (3 of 8).',
    duration_seconds: null,
    usd_cost: 0.0412,
    started_at: '2026-09-01T08:26:11.000000Z',
    completed_at: null,
    period_start: null,
    period_end: null,
    lookback_days: 7,
  },
]

export const fixtureRunDetail: PipelineRunDetail = {
  ...fixtureRuns[0],
  triggered_by: 'admin',
  reprocess_existing: false,
  tokens_in: 879394,
  tokens_out: 24944,
  total_tokens: 904338,
  papers_count: 10,
  duplicates_count: 0,
  extractions_count: 45,
  storage: { size_formatted: '3.2 MB', files: 12 },
}

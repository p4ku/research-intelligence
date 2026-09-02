/**
 * Contract-shaped pipeline-run fixtures for the skeleton gallery and tests.
 * Deterministic fake UUIDs; validated against the schemas by
 * src/lib/bff/fixtures.test.ts. Values follow what Django actually sends (the
 * local-data snapshots), not invented shapes. Pure.
 *
 * `fixtureRuns` is the runs table's drift contract and stays at three rows.
 * `fixtureOverviewRuns` adds what the Studio overview must design for:
 * runs in three workspaces, one queued, one aborted by a schedule, and a
 * same-day rerun that reprocessed existing papers.
 */
import { fixtureWorkspace } from '../papers/fixtures'
import { fixtureBudgetWorkspace, fixtureEmptyWorkspace } from '../workspaces/fixtures'
import type { PipelineRun, PipelineRunDetail } from './schema'

const manual = {
  schedule_id: null,
  schedule_name: null,
  reprocess_existing: false,
}

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
    triggered_by: 'admin',
    tokens_in: 879394,
    tokens_out: 24944,
    total_tokens: 904338,
    ...manual,
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
    triggered_by: 'admin',
    tokens_in: 402118,
    tokens_out: 9822,
    total_tokens: 411940,
    ...manual,
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
    triggered_by: 'm.fischer',
    tokens_in: 48210,
    tokens_out: 3120,
    total_tokens: 51330,
    ...manual,
  },
]

export const fixtureRunDetail: PipelineRunDetail = {
  ...fixtureRuns[0],
  papers_count: 10,
  duplicates_count: 0,
  extractions_count: 45,
  storage: { size_formatted: '3.2 MB', files: 12 },
}

const schedule = {
  schedule_id: '00000000-0000-4000-8000-000000000301',
  schedule_name: 'Weekly digest (Fri 09:00)',
}

export const fixtureOverviewRuns: PipelineRun[] = [
  ...fixtureRuns,
  // A same-day rerun of the completed run above, reprocessing existing papers.
  {
    id: '00000000-0000-4000-8000-000000000104',
    workspace_id: fixtureWorkspace.id,
    workspace_name: fixtureWorkspace.name,
    run_date: '2026-08-31',
    status: 'completed',
    current_stage: 'completed',
    total_papers_fetched: 10,
    total_papers_passed_screening: 9,
    status_message:
      'Full SLR pipeline finished successfully. Papers: 10 fetched, 9 passed screening (existing papers reprocessed).',
    duration_seconds: 211.7,
    usd_cost: 0.8014,
    started_at: '2026-08-31T13:02:48.000000Z',
    completed_at: '2026-08-31T13:06:19.700000Z',
    triggered_by: 'm.fischer',
    tokens_in: 902310,
    tokens_out: 26105,
    total_tokens: 928415,
    schedule_id: null,
    schedule_name: null,
    reprocess_existing: true,
  },
  // Aborted by an operator during full-text screening; started by a schedule.
  {
    id: '00000000-0000-4000-8000-000000000105',
    workspace_id: fixtureBudgetWorkspace.id,
    workspace_name: fixtureBudgetWorkspace.name,
    run_date: '2026-08-31',
    status: 'aborted',
    current_stage: 'full_text_screening',
    total_papers_fetched: 52,
    total_papers_passed_screening: 14,
    status_message: 'Aborted by admin during full-text screening (38 of 52 papers screened).',
    duration_seconds: 1097,
    usd_cost: 0.93,
    started_at: '2026-08-31T09:00:03.000000Z',
    completed_at: '2026-08-31T09:18:20.000000Z',
    triggered_by: null,
    tokens_in: 301700,
    tokens_out: 12800,
    total_tokens: 314500,
    reprocess_existing: false,
    ...schedule,
  },
  // Failed in download with a message worth reading.
  {
    id: '00000000-0000-4000-8000-000000000106',
    workspace_id: fixtureBudgetWorkspace.id,
    workspace_name: fixtureBudgetWorkspace.name,
    run_date: '2026-09-01',
    status: 'failed',
    current_stage: 'download',
    total_papers_fetched: 41,
    total_papers_passed_screening: 0,
    status_message:
      'PDF download failed for 7 of 22 papers after 3 retries (arxiv.org 429); run halted by operator.',
    duration_seconds: 660,
    usd_cost: 0.38,
    started_at: '2026-09-01T07:30:14.000000Z',
    completed_at: '2026-09-01T07:41:14.000000Z',
    triggered_by: 'j.brandt',
    tokens_in: 118300,
    tokens_out: 4200,
    total_tokens: 122500,
    ...manual,
  },
  // Queued: a schedule fired but no worker has picked the run up.
  {
    id: '00000000-0000-4000-8000-000000000107',
    workspace_id: fixtureBudgetWorkspace.id,
    workspace_name: fixtureBudgetWorkspace.name,
    run_date: '2026-09-01',
    status: 'pending',
    current_stage: 'search',
    total_papers_fetched: 0,
    total_papers_passed_screening: 0,
    status_message: 'Queued; waiting for a pipeline worker.',
    duration_seconds: null,
    usd_cost: 0,
    started_at: '2026-09-01T09:12:00.000000Z',
    completed_at: null,
    triggered_by: null,
    tokens_in: 0,
    tokens_out: 0,
    total_tokens: 0,
    reprocess_existing: false,
    schedule_id: '00000000-0000-4000-8000-000000000302',
    schedule_name: 'Daily scan (09:12)',
  },
]

/** The workspaces the overview fixtures span, for gallery pairs. */
export const fixtureOverviewWorkspaceIds = [
  fixtureWorkspace.id,
  fixtureEmptyWorkspace.id,
  fixtureBudgetWorkspace.id,
]

import type { PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import { describe, expect, test } from 'bun:test'
import { matches } from './run-tabs'

const baseRun: PipelineRun = {
  id: 'a2a44548-6af3-47ce-a538-724427e69e0b',
  workspace_id: '73df18b9-a897-4074-bf41-c51fca1aa5d6',
  workspace_name: 'clinical_ai_slr',
  run_date: '2026-10-26',
  status: 'running',
  current_stage: 'abstract_screening',
  total_papers_fetched: 100,
  total_papers_passed_screening: 25,
  status_message: 'Paused at checkpoint gate',
  duration_seconds: null,
  usd_cost: 0.12,
  started_at: '2026-10-26T20:00:00Z',
  completed_at: null,
  period_start: null,
  period_end: null,
  lookback_days: 7,
  retryable: true,
}

describe('RunTabs matches()', () => {
  test('includes paused SLR runs under the running tab alongside running and pending', () => {
    expect(matches({ ...baseRun, status: 'running' }, 'running')).toBe(true)
    expect(matches({ ...baseRun, status: 'pending' }, 'running')).toBe(true)
    expect(matches({ ...baseRun, status: 'paused' }, 'running')).toBe(true)
    expect(matches({ ...baseRun, status: 'completed' }, 'running')).toBe(false)
    expect(matches({ ...baseRun, status: 'failed' }, 'running')).toBe(false)
  })
})


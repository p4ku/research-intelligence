import { describe, expect, test } from 'bun:test'
import type { PipelineRun } from '../pipeline-runs/schema'
import { corpusVersion } from './version'

function run(over: Partial<PipelineRun> = {}): PipelineRun {
  return {
    id: 'r1',
    workspace_id: 'w1',
    workspace_name: 'Hybrid Computing',
    run_date: '2026-08-31',
    status: 'completed',
    current_stage: null,
    total_papers_fetched: 40,
    total_papers_passed_screening: 12,
    status_message: null,
    duration_seconds: 120,
    usd_cost: 0.5,
    started_at: '2026-08-31T09:00:00Z',
    completed_at: '2026-08-31T09:02:00Z',
    period_start: null,
    period_end: null,
    lookback_days: null,
    retryable: false,
    ...over,
  }
}

describe('corpusVersion', () => {
  test('is order-independent', () => {
    const a = run({ id: 'a' })
    const b = run({ id: 'b' })
    expect(corpusVersion([a, b])).toBe(corpusVersion([b, a]))
  })

  test('moves when a run completes, finishes, or writes papers', () => {
    const base = corpusVersion([run()])
    expect(corpusVersion([run({ status: 'running' })])).not.toBe(base)
    expect(corpusVersion([run({ completed_at: '2026-08-31T10:00:00Z' })])).not.toBe(base)
    expect(corpusVersion([run({ total_papers_fetched: 41 })])).not.toBe(base)
    expect(corpusVersion([run({ total_papers_passed_screening: 13 })])).not.toBe(base)
    expect(corpusVersion([run(), run({ id: 'r2' })])).not.toBe(base)
  })

  test('ignores the stage a running run is in', () => {
    const a = run({ status: 'running', current_stage: 'screening' })
    const b = run({ status: 'running', current_stage: 'scoring' })
    expect(corpusVersion([a])).toBe(corpusVersion([b]))
  })

  test('an empty ledger is stable and short', () => {
    expect(corpusVersion([])).toBe(corpusVersion([]))
    expect(corpusVersion([])).toHaveLength(22)
  })
})

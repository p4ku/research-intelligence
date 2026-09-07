import { describe, expect, test } from 'bun:test'
import { fixtureRuns } from '../pipeline-runs/fixtures'
import type { PipelineRun } from '../pipeline-runs/schema'
import { corpusVersion } from './version'

/** A completed fixture run, overridden per case. */
const run = (over: Partial<PipelineRun> = {}): PipelineRun => ({ ...fixtureRuns[0], ...over })

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

  test('moves with the stage a running run is in', () => {
    const a = run({ status: 'running', current_stage: 'screening' })
    const b = run({ status: 'running', current_stage: 'scoring' })
    expect(corpusVersion([a])).not.toBe(corpusVersion([b]))
  })

  test('an empty ledger is stable and short', () => {
    expect(corpusVersion([])).toBe(corpusVersion([]))
    expect(corpusVersion([])).toHaveLength(22)
  })
})

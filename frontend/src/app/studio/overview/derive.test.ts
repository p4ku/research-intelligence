import { fixtureStepsFailed } from '@/lib/bff/component-runs/fixtures'
import { fixtureWorkspace } from '@/lib/bff/papers/fixtures'
import { fixtureOverviewRuns } from '@/lib/bff/pipeline-runs/fixtures'
import { STAGES, type PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import {
  fixtureBudgetWorkspace,
  fixtureEmptyWorkspace,
  fixtureWorkspaces,
} from '@/lib/bff/workspaces/fixtures'
import { describe, expect, test } from 'bun:test'
import {
  attentionRuns,
  defaultRun,
  fmtDay,
  fmtUtc,
  groupByDay,
  indexRuns,
  notices,
  quotaPercent,
  railOrder,
  reconcileFilter,
  relativeAge,
  runMarks,
  segmentTones,
  stageForStep,
  stageSentence,
  statusCounts,
  stoppedStage,
  summariseWorkspace,
  triggerText,
} from './derive'

const NOW = '2026-09-01T09:15:00Z'
const TODAY = NOW.slice(0, 10)
const index = indexRuns(fixtureOverviewRuns)
const byId = (id: string) => index.byId.get(id)!
const RUNNING = '00000000-0000-4000-8000-000000000103'
const RERUN = '00000000-0000-4000-8000-000000000104'
const FIRST = '00000000-0000-4000-8000-000000000101'
const ABORTED = '00000000-0000-4000-8000-000000000105'
const FAILED = '00000000-0000-4000-8000-000000000106'
const PENDING = '00000000-0000-4000-8000-000000000107'

function summaries() {
  return new Map(fixtureWorkspaces.map((ws) => [ws.id, summariseWorkspace(ws, index, TODAY)]))
}

describe('index', () => {
  test('sorts newest first and never gives the latest mark to a queued run', () => {
    expect(index.all[0].id).toBe(PENDING)
    expect(index.newestInWorkspace.get(fixtureBudgetWorkspace.id)).toBe(FAILED)
    expect(index.newestInWorkspace.get(fixtureWorkspace.id)).toBe(RUNNING)
  })
  test('marks the same-day rerun as latest that day, the first run not at all', () => {
    expect(runMarks(byId(RERUN), index)).toEqual(['Latest that day', 'Reprocessed'])
    expect(runMarks(byId(FIRST), index)).toEqual([])
    expect(runMarks(byId(RUNNING), index)).toEqual(['Latest in workspace'])
    expect(runMarks(byId(PENDING), index)).toEqual([])
  })
})

describe('workspaces', () => {
  test('state: running beats attention beats ok; no runs is none', () => {
    const s = summaries()
    expect(s.get(fixtureWorkspace.id)?.state).toBe('running')
    expect(s.get(fixtureBudgetWorkspace.id)?.state).toBe('attention')
    expect(s.get(fixtureEmptyWorkspace.id)?.state).toBe('none')
  })
  test('quota percent is null without a limit', () => {
    expect(quotaPercent(10, null)).toBeNull()
    expect(quotaPercent(10, 0)).toBeNull()
    expect(quotaPercent(21.4, 25)).toBeCloseTo(85.6)
  })
  test('notices: budget at or over 80 percent, and workspaces with no runs; never e2e', () => {
    const list = notices(
      [...fixtureWorkspaces, { ...fixtureEmptyWorkspace, id: 'x', name: 'test_e2e_123' }],
      new Map([...summaries(), ['x', summariseWorkspace(fixtureEmptyWorkspace, index, TODAY)]]),
    )
    expect(list.map((n) => [n.kind, n.workspace.name])).toEqual([
      ['no-runs', fixtureEmptyWorkspace.name],
      ['budget', fixtureBudgetWorkspace.name],
    ])
  })
  test('rail order: running, attention, ok, none; e2e workspaces last', () => {
    const e2e = { ...fixtureWorkspace, id: 'e', name: 'test_e2e_1' }
    const order = railOrder(
      [e2e, ...fixtureWorkspaces],
      new Map([...summaries(), ['e', summaries().get(fixtureWorkspace.id)!]]),
    )
    expect(order.map((w) => w.id)).toEqual([
      fixtureWorkspace.id,
      fixtureBudgetWorkspace.id,
      fixtureEmptyWorkspace.id,
      'e',
    ])
  })
})

describe('runs', () => {
  test('default run: running, else a recent failure, else the newest', () => {
    expect(defaultRun(index.all, NOW)).toBe(RUNNING)
    const budget = index.byWorkspace.get(fixtureBudgetWorkspace.id)!
    expect(defaultRun(budget, NOW)).toBe(FAILED)
    // Three weeks later the failure is old news: the newest run wins.
    expect(defaultRun(budget, '2026-09-22T09:15:00Z')).toBe(PENDING)
    expect(defaultRun([], NOW)).toBeNull()
  })
  test('attention: running, failed, aborted, newest first within each', () => {
    expect(attentionRuns(index.all).map((r) => r.id)).toEqual([
      RUNNING,
      FAILED,
      '00000000-0000-4000-8000-000000000102',
      ABORTED,
    ])
  })
  test('day groups: days newest first, rows newest first across workspaces', () => {
    const groups = groupByDay(
      index.all.filter((r) => r.status === 'completed' || r.status === 'pending'),
    )
    expect(groups.map((g) => g.date)).toEqual(['2026-09-01', '2026-08-31'])
    const day = groups[1]
    expect(day.runs.map((r) => r.id)).toEqual([RERUN, FIRST])
    for (let i = 1; i < day.runs.length; i++) {
      expect(Date.parse(day.runs[i - 1].started_at!)).toBeGreaterThanOrEqual(
        Date.parse(day.runs[i].started_at!),
      )
    }
  })
  test('a filter survives a scope change only when the new scope has that status', () => {
    const counts = statusCounts(index.byWorkspace.get(fixtureWorkspace.id)!)
    expect(reconcileFilter('running', counts)).toBe('running')
    expect(reconcileFilter('aborted', counts)).toBe('all')
    expect(reconcileFilter('all', counts)).toBe('all')
  })
  test('trigger text prefers the schedule, then the user', () => {
    expect(triggerText(byId(ABORTED))).toBe('Schedule · Weekly digest (Fri 09:00)')
    expect(triggerText(byId(FAILED))).toBe('Manual · j.brandt')
    expect(triggerText({ ...byId(FAILED), triggered_by: null })).toBe('Manual')
    expect(triggerText({ ...byId(ABORTED), schedule_name: null })).toBe('Schedule')
  })
})

describe('stages', () => {
  test('screening steps split by component name', () => {
    expect(stageForStep({ step_type: 'screening', component_name: 'abstract_screening' })).toBe(
      'abstract_screening',
    )
    expect(stageForStep({ step_type: 'screening', component_name: 'full_text_screening' })).toBe(
      'full_text_screening',
    )
    expect(stageForStep({ step_type: 'metrics', component_name: 'x' })).toBeNull()
  })
  test('a failed run stops where its failed step says, never where current_stage says', () => {
    const failed = byId(FAILED)
    expect(stoppedStage(failed, fixtureStepsFailed)).toBe('download')
    expect(stoppedStage(failed, null)).toBeNull()
    expect(
      stoppedStage({ ...failed, status: 'completed', current_stage: 'search' }, null),
    ).toBeNull()
  })
  test('segments: evidence from steps when present, dispatched stage only while running', () => {
    const failedTones = segmentTones(byId(FAILED), fixtureStepsFailed)
    expect(failedTones[STAGES.indexOf('search')]).toBe('done')
    expect(failedTones[STAGES.indexOf('download')]).toBe('bad')
    expect(failedTones[STAGES.indexOf('ocr')]).toBe('idle')
    // Without steps a failed run lights nothing.
    expect(segmentTones(byId(FAILED), null).every((t) => t === 'idle')).toBe(true)
    const running = segmentTones(byId(RUNNING), null)
    expect(running.slice(0, STAGES.indexOf('abstract_screening'))).toEqual(['done', 'done', 'done'])
    expect(running[STAGES.indexOf('abstract_screening')]).toBe('now')
    // A completed run lights nothing from current_stage either.
    expect(segmentTones(byId(RERUN), null).every((t) => t === 'idle')).toBe(true)
  })
  test('sentences', () => {
    expect(stageSentence(byId(RUNNING), null, NOW)).toBe(
      'Abstract screening, stage 4 of 8 · run started 08:26 UTC, 49m ago',
    )
    expect(stageSentence(byId(FAILED), fixtureStepsFailed, NOW)).toBe(
      'Stopped in Download, stage 2 of 8',
    )
    expect(stageSentence(byId(FAILED), null, NOW)).toBe('Last stage dispatched · Download')
    expect(stageSentence(byId(PENDING), null, NOW)).toBe(
      'Queued at Search · nothing dispatched yet',
    )
    expect(stageSentence(byId(RERUN), null, NOW)).toBe('Completed')
  })
})

describe('time', () => {
  test('formats in UTC regardless of the process zone', () => {
    expect(fmtUtc('2026-09-02T09:15:00Z')).toBe('2 Sep 2026, 09:15 UTC')
    expect(fmtUtc('2026-09-02T23:59:00+02:00')).toBe('2 Sep 2026, 21:59 UTC')
    expect(fmtDay('2026-09-02')).toBe('Wed 2 Sep 2026')
    expect(fmtUtc('nope')).toBe('—')
  })
  test('relative age against the clock it is given', () => {
    expect(relativeAge('2026-09-01T09:14:30Z', NOW)).toBe('30s ago')
    expect(relativeAge('2026-09-01T08:26:11Z', NOW)).toBe('49m ago')
    expect(relativeAge('2026-08-31T09:15:00Z', NOW)).toBe('1d ago')
    expect(relativeAge('2026-09-01T09:16:00Z', NOW)).toBe('just now')
  })
})

// Type-only guard: the fixture is the contract shape the page receives.
const _run: PipelineRun = fixtureOverviewRuns[0]
void _run

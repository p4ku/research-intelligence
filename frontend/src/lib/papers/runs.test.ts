import { fixturePapers } from '@/lib/bff/papers/fixtures'
import { describe, expect, test } from 'bun:test'
import { indexRuns, papersOfRun } from './runs'

const OLD = '00000000-0000-4000-8000-0000000000a1'
const NEW = '00000000-0000-4000-8000-0000000000a2'

const metric = (pipeline_run: string, extra: Record<string, unknown> = {}) => ({
  id: `${pipeline_run}-m`,
  paper: 'p',
  pipeline_run,
  workspace: 'w',
  signal_score: null,
  signal_score_details: {},
  metrics_data: {},
  created_at: '2026-09-03T08:00:00Z',
  ...extra,
})

// The corpus as Django serves it: `pipeline_run_id` is the run that saw the
// paper last, whatever the run that briefed it.
const [a, b] = fixturePapers
const corpus = new Map([
  [a.id, { ...a, pipeline_run_id: NEW, screening_status: 'accepted' as const, signal_score: 90 }],
  [b.id, { ...b, pipeline_run_id: NEW, screening_status: 'rejected' as const, signal_score: null }],
])

describe('indexRuns', () => {
  test('one record per (run, paper), from the run’s own metric row', () => {
    const index = indexRuns([
      {
        id: a.id,
        metrics: [
          metric(OLD, { screening_status: 'accepted', signal_score: 71.5 }),
          metric(NEW, { screening_status: 'rejected', full_text_screening_reasoning: 'Off topic' }),
        ],
      },
      { id: b.id, metrics: [metric(NEW, { screening_status: 'withdrawn' })] },
    ])
    expect([...index.keys()]).toEqual([OLD, NEW])
    expect(index.get(OLD)?.get(a.id)).toEqual({
      screening_status: 'accepted',
      screening_reasoning: null,
      signal_score: 71.5,
    })
    expect(index.get(NEW)?.get(a.id)).toMatchObject({
      screening_status: 'rejected',
      screening_reasoning: 'Off topic',
    })
    expect(index.get(NEW)?.has(b.id)).toBe(true)
  })

  test('a metric without a run, or without a decision, is indexed honestly', () => {
    const index = indexRuns([
      { id: a.id, metrics: [metric(OLD), { ...metric(NEW), pipeline_run: null }] },
    ])
    expect(index.has(NEW)).toBe(false)
    expect(index.get(OLD)?.get(a.id)?.screening_status).toBeNull()
  })
})

describe('papersOfRun', () => {
  test('an older run keeps its papers, as it recorded them', () => {
    const index = indexRuns([
      { id: a.id, metrics: [metric(OLD, { screening_status: 'accepted', signal_score: 71.5 })] },
    ])
    const [only, ...rest] = papersOfRun(OLD, corpus, index)
    expect(rest).toEqual([])
    expect(only.paper.id).toBe(a.id)
    expect(only.status).toBe('accepted')
    expect(only.signal_score).toBe(71.5)
    // The newest run recorded nothing about it (the index, not the corpus, decides).
    expect(papersOfRun(NEW, corpus, index)).toEqual([])
  })

  test('a row without a decision takes the paper’s current one; reasoning and score stay the run’s', () => {
    const index = indexRuns([{ id: b.id, metrics: [metric(OLD)] }])
    const [only] = papersOfRun(OLD, corpus, index)
    expect(only.status).toBe('rejected')
    // A later run's words never land in this run's screening log.
    expect(only.reason).toBeNull()
    expect(only.signal_score).toBeNull()
  })

  test('two rows for one (run, paper): the newest wins, in either arrival order', () => {
    const older = metric(OLD, { screening_status: 'rejected', created_at: '2026-09-01T00:00:00Z' })
    const newer = metric(OLD, { screening_status: 'accepted', created_at: '2026-09-02T00:00:00Z' })
    for (const metrics of [
      [older, newer],
      [newer, older],
    ]) {
      const index = indexRuns([{ id: a.id, metrics }])
      expect(index.get(OLD)?.get(a.id)?.screening_status).toBe('accepted')
    }
  })

  test('a paper the corpus cannot see is skipped', () => {
    const index = indexRuns([{ id: 'gone', metrics: [metric(OLD)] }])
    expect(papersOfRun(OLD, corpus, index)).toEqual([])
  })

  test('without an index the corpus’s own attribution stands', () => {
    const ids = papersOfRun(NEW, corpus, null).map((r) => r.paper.id)
    expect(ids).toEqual([a.id, b.id])
    expect(papersOfRun(OLD, corpus, null)).toEqual([])
  })
})

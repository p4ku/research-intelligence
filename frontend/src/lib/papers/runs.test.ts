import { fixturePapers } from '@/lib/bff/papers/fixtures'
import { describe, expect, test } from 'bun:test'
import { indexRuns, paperAsRun, papersOfRun } from './runs'

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
      abstract_screening_reasoning: null,
      full_text_screening_reasoning: null,
      signal_score: 71.5,
    })
    expect(index.get(NEW)?.get(a.id)).toMatchObject({
      screening_status: 'rejected',
      screening_reasoning: 'Off topic',
      abstract_screening_reasoning: null,
      full_text_screening_reasoning: 'Off topic',
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

  test('a row without a decision takes the paper’s current one; the score stays the run’s', () => {
    const index = indexRuns([{ id: b.id, metrics: [metric(OLD)] }])
    const [only] = papersOfRun(OLD, corpus, index)
    expect(only.status).toBe('rejected')
    expect(only.signal_score).toBeNull()
  })

  test('a row without reasoning takes the paper’s only when the paper reports this run', () => {
    const index = indexRuns([{ id: b.id, metrics: [metric(OLD), metric(NEW)] }])
    // The paper reports NEW: its reasoning is NEW's, and must not land in OLD's log.
    expect(papersOfRun(OLD, corpus, index)[0].reason).toBeNull()
    expect(papersOfRun(NEW, corpus, index)[0].reason).toBe(b.screening_reasoning)
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

describe('paperAsRun', () => {
  const paper = corpus.get(a.id)!
  const index = indexRuns([
    {
      id: a.id,
      metrics: [
        metric(OLD, {
          screening_status: 'accepted',
          signal_score: 71.5,
          abstract_screening_reasoning: 'On topic',
          full_text_screening_reasoning: 'Solid method',
        }),
        metric(NEW, { screening_status: 'rejected', full_text_screening_reasoning: 'Off topic' }),
      ],
    },
  ])

  test('the run the corpus already reports needs no overlay', () => {
    expect(paperAsRun(paper, NEW, index, null)).toBe(paper)
    expect(paperAsRun(paper, NEW, null, null)).toBe(paper)
  })

  test('an older run’s row: its decision, score, stage reasons and provenance', () => {
    const asOld = paperAsRun(paper, OLD, index, null)
    expect(asOld).toMatchObject({
      id: a.id,
      pipeline_run_id: OLD,
      pipeline_run_name: null,
      screening_status: 'accepted',
      signal_score: 71.5,
      screening_reasoning: 'Solid method',
      abstract_screening_reasoning: 'On topic',
      full_text_screening_reasoning: 'Solid method',
    })
    // Everything else is the paper's: extractions belong to it, not to a run.
    expect(asOld?.dimensions).toBe(paper.dimensions)
    expect(asOld?.title).toBe(paper.title)
  })

  test('past the corpus cap the edition’s entry stands in, with the reasons withheld', () => {
    const asOld = paperAsRun(paper, OLD, null, { screening_status: 'accepted', signal_score: 68 })
    expect(asOld).toMatchObject({
      pipeline_run_id: OLD,
      screening_status: 'accepted',
      signal_score: 68,
      screening_reasoning: null,
      abstract_screening_reasoning: null,
      full_text_screening_reasoning: null,
    })
    // An entry without a decision (the serializer lag) keeps the paper's.
    expect(paperAsRun(paper, OLD, null, { signal_score: 68 })?.screening_status).toBe('accepted')
  })

  test('a run that never recorded the paper is null — the page shows the paper as it stands', () => {
    const other = '00000000-0000-4000-8000-0000000000a3'
    expect(paperAsRun(paper, other, index, null)).toBeNull()
    expect(paperAsRun(paper, other, null, undefined)).toBeNull()
  })
})

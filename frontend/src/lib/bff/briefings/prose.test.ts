import { describe, expect, test } from 'bun:test'
import { templateProse } from './prose'

const paper = (title: string, signal: number | null) => ({
  id: '00000000-0000-4000-8000-000000000001',
  title,
  authors: [],
  source: 'arxiv',
  screening_status: 'accepted' as const,
  signal_score: signal,
})

describe('templateProse', () => {
  test('full run', () => {
    const p = templateProse({
      workspaceName: 'Agentic AI Scan',
      fetched: 12,
      passedScreening: 5,
      surfaced: 3,
      papers: [paper('Big Result: with subtitle', 87.5), paper('Second', 70), paper('Third', 60)],
    })
    expect(p.title).toBe('Big Result')
    expect(p.in_brief).toContain('fetched 12 papers')
    expect(p.in_brief).toContain('“Big Result” at signal 88')
    expect(p.in_brief).toContain('Also notable: “Second” and “Third”.')
  })
  test('the leading score is the whole number the card prints', () => {
    const p = templateProse({
      workspaceName: 'Scan',
      fetched: 3,
      passedScreening: 2,
      surfaced: 1,
      papers: [paper('Edge', 74.6)],
    })
    expect(p.in_brief).toContain('“Edge” at signal 75')
    expect(p.in_brief).not.toContain('74.6')
  })
  test('empty run', () => {
    const p = templateProse({
      workspaceName: 'Scan',
      fetched: 1,
      passedScreening: 0,
      surfaced: 0,
      papers: [],
    })
    expect(p.title).toBe('A quiet run')
    expect(p.in_brief).toContain('fetched 1 paper;')
  })
  test('a run that passed papers the edition cannot show does not claim none passed', () => {
    const p = templateProse({
      workspaceName: 'Hybrid Computing',
      fetched: 94,
      passedScreening: 25,
      surfaced: 0,
      papers: [],
    })
    expect(p.title).toBe('Papers not on file')
    expect(p.in_brief).toBe(
      'The Hybrid Computing scan fetched 94 papers and passed 25 through screening; none of them are on file for this briefing.',
    )
    const de = templateProse(
      {
        workspaceName: 'Hybrid Computing',
        fetched: 94,
        passedScreening: 25,
        surfaced: 0,
        papers: [],
      },
      'de',
    )
    expect(de.title).toBe('Papers nicht hinterlegt')
    expect(de.in_brief).toContain('und 25 durch das Screening gebracht; keines davon liegt')
  })
  test('unscored leader has no signal clause', () => {
    const p = templateProse({
      workspaceName: 'Scan',
      fetched: 3,
      passedScreening: 1,
      surfaced: 1,
      papers: [paper('Solo', null)],
    })
    expect(p.in_brief).not.toContain('at signal')
  })
  test('full run, German', () => {
    const p = templateProse(
      {
        workspaceName: 'Agentic AI Scan',
        fetched: 12,
        passedScreening: 5,
        surfaced: 3,
        papers: [paper('Big Result: with subtitle', 87.5), paper('Second', 70), paper('Third', 60)],
      },
      'de',
    )
    expect(p.title).toBe('Big Result')
    expect(p.in_brief).toContain('„Agentic AI Scan“ hat 12 Papers geladen')
    expect(p.in_brief).toContain('An der Spitze: „Big Result“ mit Signal 88.')
    expect(p.in_brief).toContain('Ebenfalls bemerkenswert: „Second“ und „Third“.')
  })
  test('empty run, German singular', () => {
    const p = templateProse(
      { workspaceName: 'Scan', fetched: 1, passedScreening: 0, surfaced: 0, papers: [] },
      'de',
    )
    expect(p.title).toBe('Ein ruhiger Lauf')
    expect(p.in_brief).toContain('hat 1 Paper geladen;')
    expect(p.in_brief).toContain('keines hat das Screening')
  })
})

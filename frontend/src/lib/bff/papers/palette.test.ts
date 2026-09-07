import { describe, expect, test } from 'bun:test'
import { fixturePapers } from './fixtures'
import { toPalette, toPaletteEntry } from './palette'

describe('toPalette', () => {
  test('projects a paper to the picker row', () => {
    const paper = fixturePapers[0]!
    expect(toPaletteEntry(paper)).toEqual({
      id: paper.id,
      title: paper.title,
      first_author: paper.authors[0] ?? null,
      source: paper.source,
      signal_score: paper.signal_score,
      created_at: paper.created_at,
    })
  })

  test('orders by signal, best first, unscored last', () => {
    const base = fixturePapers[0]!
    const papers = [
      { ...base, id: '00000000-0000-4000-8000-000000000001', signal_score: 40 },
      { ...base, id: '00000000-0000-4000-8000-000000000002', signal_score: null },
      { ...base, id: '00000000-0000-4000-8000-000000000003', signal_score: 90 },
    ]
    expect(toPalette({ papers }).papers.map((p) => p.signal_score)).toEqual([90, 40, null])
  })

  test('an authorless paper has no first author', () => {
    expect(toPaletteEntry({ ...fixturePapers[0]!, authors: [] }).first_author).toBeNull()
  })
})

import { describe, expect, test } from 'bun:test'
import { fixturePapers } from './fixtures'
import { toPalette, toPaletteEntry } from './palette'

const base = fixturePapers[0]!
const id = (n: number) => `00000000-0000-4000-8000-00000000000${n}`

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

  test('an empty query orders by signal, best first, unscored last, and counts everything', () => {
    const papers = [
      { ...base, id: id(1), signal_score: 40 },
      { ...base, id: id(2), signal_score: null },
      { ...base, id: id(3), signal_score: 90 },
    ]
    const palette = toPalette({ papers })
    expect(palette.papers.map((p) => p.signal_score)).toEqual([90, 40, null])
    expect(palette).toMatchObject({ query: '', matched: 3, total: 3 })
  })

  test('a query goes through the shared matcher: a stem or prefix hit counts', () => {
    // Titles only: the fixture's shared abstract would match everything.
    const plain = { ...base, abstract: '', authors: [] as string[] }
    const papers = [
      { ...plain, id: id(1), title: 'Multi-Agent Planning for Warehouses', signal_score: 10 },
      { ...plain, id: id(2), title: 'Battery Chemistry Review', signal_score: 90 },
      { ...plain, id: id(3), title: 'Agents That Negotiate', signal_score: 50 },
    ]
    const palette = toPalette({ papers }, { q: 'agents', limit: 20 })
    expect(palette.papers.map((p) => p.id).sort()).toEqual([id(1), id(3)])
    expect(palette).toMatchObject({ query: 'agents', matched: 2, total: 3 })
  })

  test('the limit cuts the rows but not the counts', () => {
    const papers = [1, 2, 3, 4].map((n) => ({ ...base, id: id(n), signal_score: n * 10 }))
    const palette = toPalette({ papers }, { q: '', limit: 2 })
    expect(palette.papers.map((p) => p.signal_score)).toEqual([40, 30])
    expect(palette).toMatchObject({ matched: 4, total: 4 })
  })

  test('an authorless paper has no first author', () => {
    expect(toPaletteEntry({ ...fixturePapers[0]!, authors: [] }).first_author).toBeNull()
  })
})

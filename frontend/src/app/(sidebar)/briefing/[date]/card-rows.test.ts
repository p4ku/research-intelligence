import { fixturePapers } from '@/lib/bff/papers/fixtures'
import type { ScoredPaper } from '@/lib/papers/types'
import { describe, expect, test } from 'bun:test'
import { ABSTRACT_CHARS, cardRow, cardRows } from './card-rows'

const heavy: ScoredPaper = {
  ...fixturePapers[0]!,
  abstract: 'word '.repeat(400),
  authors_raw: 'A, B, C',
  screening_reasoning: 'long reasoning',
  abstract_screening_reasoning: 'stage one',
  full_text_screening_reasoning: 'stage two',
  pdf_key: 'papers/x.pdf',
  markdown_key: 'papers/x.md',
  summary: 'a paragraph',
  dimensions: [
    {
      key: 'research_metrics',
      definition_id: null,
      name: 'Research Metrics',
      label: 'Research Metrics',
      value: 72,
      raw: '72',
      max: 100,
      is_trl: false,
      order: 1,
      is_risk_and_affiliation: false,
      response_schema: { type: 'object', properties: { big: { type: 'string' } } },
      primary_metric: { key: 'novelty' },
      evidence: ['a', 'b'],
      rationale: 'because',
      model: 'google/gemini-3.8-flash',
    },
    { key: 'trl', definition_id: null, name: 'TRL', value: 4, max: 9, is_trl: true },
    // Unscored: draws nothing on the card and sorts like a missing one.
    {
      key: 'schwarz_fit',
      definition_id: null,
      name: 'Schwarz Fit',
      value: null,
      raw: '—',
      max: 100,
      is_trl: false,
      response_schema: { type: 'object' },
    },
  ],
}

describe('cardRow', () => {
  test('keeps what the card and the rail read', () => {
    const row = cardRow(heavy)
    expect(row.id).toBe(heavy.id)
    expect(row.title).toBe(heavy.title)
    expect(row.authors).toEqual(heavy.authors)
    expect(row.signal_score).toBe(heavy.signal_score)
    expect(row.screening_status).toBe(heavy.screening_status)
    expect(row.published_date).toBe(heavy.published_date)
    expect(row.created_at).toBe(heavy.created_at)
    expect(row.source).toBe(heavy.source)
    expect(row.dimensions).toEqual([
      {
        key: 'research_metrics',
        definition_id: null,
        name: 'Research Metrics',
        label: 'Research Metrics',
        value: 72,
        raw: '72',
        max: 100,
        is_trl: false,
        order: 1,
        is_risk_and_affiliation: false,
      },
      { key: 'trl', definition_id: null, name: 'TRL', value: 4, max: 9, is_trl: true },
    ])
  })

  test('drops what no card shows and cuts the abstract', () => {
    const row = cardRow(heavy)
    expect(row.abstract).toHaveLength(ABSTRACT_CHARS)
    expect(row.authors_raw).toBe('')
    expect(row.screening_reasoning).toBeNull()
    expect(row.abstract_screening_reasoning).toBeNull()
    expect(row.full_text_screening_reasoning).toBeNull()
    expect(row.signal_score_details).toBeNull()
    expect(row.pdf_key).toBeNull()
    expect(row.markdown_key).toBeNull()
    expect(row.summary).toBeNull()
    expect(row.risk_and_affiliation).toBeNull()
    expect(JSON.stringify(row).length).toBeLessThan(JSON.stringify(heavy).length / 2)
  })

  test('a short abstract is kept whole and the input is not touched', () => {
    const short = { ...heavy, abstract: 'Brief.' }
    expect(cardRow(short).abstract).toBe('Brief.')
    expect(heavy.dimensions[0]!.response_schema).toBeDefined()
    expect(cardRows([heavy, short])).toHaveLength(2)
  })
})

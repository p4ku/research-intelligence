import { describe, expect, test } from 'bun:test'
import { chronologically, labelFor, toCost, toSummary } from './normalise'
import type { ComponentRun } from './schema'

/**
 * Shapes below are copied from the 2026-09-01 production snapshot
 * (the `api/component-runs` index under `local-data/`, 99 rows), not
 * invented — the point of this module is to survive what the engine actually
 * writes.
 */

describe('toSummary', () => {
  test('search picks one duplicate count out of the five keys the engine writes', () => {
    // Real payload writes all five, all equal; earlier engines wrote a subset.
    expect(
      toSummary(
        'search',
        {
          duplicates: 2,
          total_found: 5,
          ingested_new: 3,
          total_created: 3,
          total_fetched: 5,
          duplicates_count: 2,
          total_duplicates: 2,
          duplicates_skipped: 2,
          total_duplicates_skipped: 2,
        },
        {},
      ),
    ).toEqual({ kind: 'search', created: 3, fetched: 5, duplicates: 2 })
  })

  test('search falls back through key variants when only the older ones exist', () => {
    expect(
      toSummary('search', { total_created: 4, total_found: 9, total_duplicates: 5 }, {}),
    ).toEqual({ kind: 'search', created: 4, fetched: 9, duplicates: 5 })
  })

  test('screening reads the counts the engine records', () => {
    expect(
      toSummary(
        'screening',
        { failed: 0, passed: 1, rejected: 2, withdrawn: 0, total_screened: 3 },
        {},
      ),
    ).toEqual({ kind: 'screening', screened: 3, passed: 1, rejected: 2, withdrawn: 0 })
  })

  test('a skipped OCR step reports no metrics rather than a fabricated zero', () => {
    // Every OCR component in the snapshot writes exactly this.
    expect(toSummary('ocr', { status: 'skipped' }, {})).toEqual({ kind: 'none' })
  })

  test('a real OCR step reports its counts', () => {
    expect(toSummary('ocr', { ocr_converted: 7, failed: 1 }, {})).toEqual({
      kind: 'ocr',
      converted: 7,
      failed: 1,
    })
  })

  test('a successful OCR step with zero failures still reports its count', () => {
    // The Django admin renders a dash here: its failure branch has no
    // success path, so a clean OCR step shows nothing at all.
    expect(toSummary('ocr', { ocr_converted: 12, failed: 0 }, {})).toEqual({
      kind: 'ocr',
      converted: 12,
      failed: 0,
    })
  })

  test('signal_score accepts either name for the same number', () => {
    expect(
      toSummary(
        'signal_score',
        { scored_count: 3, total_papers: 3, avg_signal_score: 41.7, max_signal_score: 62 },
        {},
      ),
    ).toEqual({ kind: 'signal_score', scored: 3, total: 3, avg: 41.7, max: 62 })
    expect(
      toSummary('signal_score', { papers_scored: 2, total_papers: 2, top_score: 88 }, {}),
    ).toEqual({ kind: 'signal_score', scored: 2, total: 2, avg: null, max: 88 })
  })

  test('reporting reads output_data when metrics is thin', () => {
    expect(
      toSummary(
        'reporting',
        { report_generated: true, report_id: 'r1' },
        { characters_count: 1742, success: true },
      ),
    ).toEqual({ kind: 'reporting', generated: true, characters: 1742 })
  })

  test('empty, null and non-object metrics all resolve to none', () => {
    expect(toSummary('extraction', {}, {})).toEqual({ kind: 'none' })
    expect(toSummary('extraction', null, undefined)).toEqual({ kind: 'none' })
    expect(toSummary('screening', 'nonsense', 42)).toEqual({ kind: 'none' })
  })

  test('metrics wins over output_data when both carry a key', () => {
    expect(
      toSummary('screening', { total_screened: 3, passed: 1, rejected: 2 }, { passed: 99 }),
    ).toEqual({ kind: 'screening', screened: 3, passed: 1, rejected: 2, withdrawn: 0 })
  })
})

describe('toCost', () => {
  test('reads measured spend', () => {
    expect(
      toCost(
        {
          usd_cost: 0.0337,
          tokens_in: 38917,
          tokens_out: 1191,
          total_tokens: 40108,
          model_used: 'google/gemini-2.5-flash',
        },
        {},
      ),
    ).toEqual({
      usd: 0.0337,
      tokens_in: 38917,
      tokens_out: 1191,
      total_tokens: 40108,
      model: 'google/gemini-2.5-flash',
    })
  })

  test('a step that recorded no spend reports null, never $0.0000', () => {
    // Five of the seven step types legitimately record no cost. The admin
    // renders "$0.0000" for these, which reads as a measurement of zero.
    expect(toCost({ downloaded: 3, cached: 0 }, {})).toEqual({
      usd: null,
      tokens_in: null,
      tokens_out: null,
      total_tokens: null,
      model: null,
    })
  })

  test('derives a total from the parts, but never a cost from the tokens', () => {
    const cost = toCost({ tokens_in: 100, tokens_out: 20 }, {})
    expect(cost.total_tokens).toBe(120)
    expect(cost.usd).toBeNull()
  })

  test('parses a decimal delivered as a string', () => {
    expect(toCost({ usd_cost: '0.1760' }, {}).usd).toBe(0.176)
  })
})

describe('labelFor', () => {
  test('distinguishes the two screening components sharing one step type', () => {
    expect(labelFor('screening', 'abstract_screening')).toBe('Abstract screening')
    expect(labelFor('screening', 'full_text_screening')).toBe('Full-text screening')
  })

  test('falls back to the step type for an unknown component', () => {
    expect(labelFor('screening', 'some_future_screener')).toBe('Screening')
  })
})

describe('chronologically', () => {
  test('orders by instant, not by string, when one side has no fraction', () => {
    // DRF drops the fraction at zero microseconds, so as strings the earlier
    // step sorts last ('Z' > '.').
    const at = (step_type: ComponentRun['step_type'], started_at: string) =>
      ({ step_type, started_at }) as ComponentRun
    const search = at('search', '2026-09-08T10:00:00Z')
    const download = at('download', '2026-09-08T10:00:00.412000Z')
    expect([download, search].sort(chronologically)).toEqual([search, download])
  })

  test('a rerun of one step 400µs later keeps its attempt order', () => {
    // Django lists newest first; the timeline must not inherit that on a
    // millisecond tie, or the later attempt is labelled "Attempt 1".
    const at = (step_type: ComponentRun['step_type'], started_at: string) =>
      ({ step_type, started_at }) as ComponentRun
    const first = at('ocr', '2026-09-08T10:00:00.412300Z')
    const second = at('ocr', '2026-09-08T10:00:00.412700Z')
    expect([second, first].sort(chronologically)).toEqual([first, second])
  })

  test('equal or unparseable instants fall through to the nominal step order', () => {
    const at = (step_type: ComponentRun['step_type'], started_at: string) =>
      ({ step_type, started_at }) as ComponentRun
    const same = '2026-09-08T10:00:00Z'
    expect([at('download', same), at('search', same)].sort(chronologically)).toEqual([
      at('search', same),
      at('download', same),
    ])
    expect([at('download', 'garbage'), at('search', same)].sort(chronologically)).toEqual([
      at('search', same),
      at('download', 'garbage'),
    ])
  })
})

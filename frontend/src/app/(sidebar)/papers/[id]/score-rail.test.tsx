import { makeT } from '@/lib/i18n'
import type { ScoredPaper } from '@/lib/papers/types'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { isDisplayableRailDimension, ScoreRail } from './score-rail'

const t = makeT('en')

function mockPaper(overrides: Partial<ScoredPaper> = {}): ScoredPaper {
  return {
    id: '00000000-0000-4000-8000-000000000041',
    workspace_id: '00000000-0000-4000-8000-000000000001',
    pipeline_run_id: '00000000-0000-4000-8000-000000000031',
    title: 'Test Paper for ScoreRail',
    authors: ['A. Scientist'],
    authors_raw: 'A. Scientist',
    abstract: 'Abstract for test paper',
    doi: null,
    arxiv_id: '2608.12345',
    source: 'arxiv',
    screening_status: 'full_text_passed',
    screening_reasoning: 'Relevant topic',
    abstract_screening_reasoning: null,
    full_text_screening_reasoning: null,
    signal_score: 84.6,
    signal_score_details: null,
    dimensions: [
      {
        key: 'fit_score',
        definition_id: '00000000-0000-4000-8000-000000000011',
        name: 'Fit Score',
        value: 92,
        raw: '92',
        max: 100,
        is_trl: false,
      },
      {
        key: 'trl_level',
        definition_id: '00000000-0000-4000-8000-000000000012',
        name: 'TRL Level',
        value: 4,
        raw: 'TRL 4',
        max: 9,
        is_trl: true,
      },
      {
        key: 'novelty_score',
        definition_id: '00000000-0000-4000-8000-000000000013',
        name: 'Novelty Score',
        value: 75,
        raw: '75',
        max: 100,
        is_trl: false,
      },
    ],
    pdf_key: null,
    markdown_key: null,
    source_url: 'https://arxiv.org/abs/2608.12345',
    is_benchmark: false,
    evaluation_label: null,
    published_date: '2026-08-20',
    created_at: '2026-08-27T05:00:00Z',
    pipeline_run_name: 'Scheduled Run',
    ...overrides,
  }
}

describe('ScoreRail Component Rendering', () => {
  test('renders the Total score as a whole number and its label', () => {
    const paper = mockPaper({ signal_score: 84.6 })
    const out = renderToStaticMarkup(<ScoreRail paper={paper} t={t} />)
    expect(out).toContain('85')
    expect(out).not.toContain('84.6')
    expect(out).toContain('Total Score')
  })

  test('formats integer score without trailing zero and null score as dash', () => {
    const intPaper = mockPaper({ signal_score: 90 })
    const outInt = renderToStaticMarkup(<ScoreRail paper={intPaper} t={t} />)
    expect(outInt).toContain('90')

    const nullPaper = mockPaper({ signal_score: null })
    const outNull = renderToStaticMarkup(<ScoreRail paper={nullPaper} t={t} />)
    expect(outNull).toContain('—')
  })

  test('renders TRL badge chip without screening status pill', () => {
    const paper = mockPaper()
    const out = renderToStaticMarkup(<ScoreRail paper={paper} t={t} />)
    expect(out).toContain('TRL 4')
    expect(out).not.toContain('Full text passed')
  })

  test('renders dimension bars linking to definition anchors', () => {
    const paper = mockPaper()
    const out = renderToStaticMarkup(<ScoreRail paper={paper} t={t} />)
    // "Fit Score" is one of the names dimensionLabel maps, so the bar prints
    // the product's own spelling ("Fit-Score" in German) rather than the
    // backend's casing — the same reading the assessment heading gives it.
    expect(out).toContain('Fit score')
    expect(out).toContain('TRL')
    expect(out).toContain('Novelty Score')
    expect(out).toContain('href="#dimension-fit_score"')
    expect(out).toContain('href="#dimension-trl_level"')
    expect(out).toContain('href="#dimension-novelty_score"')
  })

  test('filters out risk and affiliation dimensions from the rail bars', () => {
    const paperWithRisk = mockPaper({
      dimensions: [
        ...mockPaper().dimensions,
        {
          key: 'risk_and_affiliation',
          definition_id: null,
          name: 'Risk & Affiliation',
          value: null,
          raw: '—',
          max: null,
          is_trl: false,
          is_risk_and_affiliation: true,
        },
      ],
    })
    const out = renderToStaticMarkup(<ScoreRail paper={paperWithRisk} t={t} />)
    expect(out).not.toContain('href="#dimension-risk_and_affiliation"')
  })

  test('renders radar chart when 3 or more numeric dimensions exist', () => {
    const paper = mockPaper() // has 3 numeric dimensions
    const out = renderToStaticMarkup(<ScoreRail paper={paper} t={t} />)
    expect(out).toContain('data-row="radar"')
    expect(out).toContain('<svg')
  })

  test('omits radar chart when fewer than 3 numeric dimensions exist', () => {
    const paperFewDims = mockPaper({
      dimensions: [
        {
          key: 'fit_score',
          definition_id: null,
          name: 'Fit Score',
          value: 92,
          raw: '92',
          max: 100,
          is_trl: false,
        },
        {
          key: 'trl_level',
          definition_id: null,
          name: 'TRL Level',
          value: 4,
          raw: 'TRL 4',
          max: 9,
          is_trl: true,
        },
      ],
    })
    const out = renderToStaticMarkup(<ScoreRail paper={paperFewDims} t={t} />)
    expect(out).not.toContain('data-row="radar"')
  })

  test('does not render scoring formula collapsible disclosure even when signal_score_details contains code_snippet', () => {
    const paper = mockPaper({
      signal_score_details: {
        code_snippet: '0.6 * trl_level + 0.4 * fit_score',
        variables: { trl_level: 4, fit_score: 92 },
        calculated_at: '2026-09-08T22:00:00Z',
        error: null,
      },
    })
    const out = renderToStaticMarkup(<ScoreRail paper={paper} t={t} />)
    expect(out).not.toContain('data-row="formula"')
    expect(out).not.toContain('Scoring formula')
    expect(out).not.toContain('0.6 * trl_level + 0.4 * fit_score')
  })

  test('isDisplayableRailDimension checks data types intelligently (int/float allowed, null/string/undefined/NaN rejected)', () => {
    // 1. Value is null (e.g. Summarisation, qualitative prose, or unscored/failed extraction) -> false
    expect(
      isDisplayableRailDimension({
        key: 'summarisation',
        definition_id: null,
        name: 'Summarisation',
        value: null,
        raw: 'This paper presents Backline...',
        max: 100,
        is_trl: false,
      }),
    ).toBe(false)

    expect(
      isDisplayableRailDimension({
        key: 'null_metric',
        definition_id: null,
        name: 'Null Metric',
        value: null,
        raw: null,
        max: null,
        is_trl: false,
      }),
    ).toBe(false)

    expect(
      isDisplayableRailDimension({
        key: 'pending_metric',
        definition_id: null,
        name: 'Pending Metric',
        value: null,
        raw: '—',
        max: 100,
        is_trl: false,
      }),
    ).toBe(false)

    // 2. Value is string or undefined or NaN (non-numeric) -> false
    expect(
      isDisplayableRailDimension({
        key: 'string_metric',
        definition_id: null,
        name: 'String Metric',
        value: 'High' as unknown as number,
        raw: 'High',
        max: 100,
        is_trl: false,
      }),
    ).toBe(false)

    expect(
      isDisplayableRailDimension({
        key: 'nan_metric',
        definition_id: null,
        name: 'NaN Metric',
        value: NaN,
        raw: 'NaN',
        max: 100,
        is_trl: false,
      }),
    ).toBe(false)

    expect(
      isDisplayableRailDimension({
        key: 'undefined_metric',
        definition_id: null,
        name: 'Undefined Metric',
        value: undefined as unknown as number,
        raw: null,
        max: 100,
        is_trl: false,
      }),
    ).toBe(false)

    // 3. CRITICAL: Score of 0 is a valid integer ("nie 0 ale niczego do wyswietlania") -> true
    expect(
      isDisplayableRailDimension({
        key: 'zero_score',
        definition_id: null,
        name: 'Zero Score Metric',
        value: 0,
        raw: '0',
        max: 100,
        is_trl: false,
      }),
    ).toBe(true)

    // 4. Positive int or float score -> true
    expect(
      isDisplayableRailDimension({
        key: 'int_metric',
        definition_id: null,
        name: 'TRL Level',
        value: 4,
        raw: 'TRL 4',
        max: 9,
        is_trl: true,
      }),
    ).toBe(true)

    expect(
      isDisplayableRailDimension({
        key: 'float_metric',
        definition_id: null,
        name: 'Research Metric',
        value: 58.67,
        raw: '58.67',
        max: 100,
        is_trl: false,
      }),
    ).toBe(true)
  })

  test('omits Summarisation and empty unscored extractions from rail bars and radar chart, while preserving score of 0', () => {
    const paperWithScreenshotScenario = mockPaper({
      signal_score: 42.8,
      dimensions: [
        {
          key: 'research_metric',
          definition_id: '00000000-0000-4000-8000-000000000091',
          name: 'Research Metric',
          value: 58.67,
          raw: '58.67',
          max: 100,
          is_trl: false,
          order: 1,
        },
        {
          key: 'schwarz_fit',
          definition_id: '00000000-0000-4000-8000-000000000092',
          name: 'Schwarz Fit',
          value: 27,
          raw: '27',
          max: 100,
          is_trl: false,
          order: 2,
        },
        {
          key: 'trl',
          definition_id: '00000000-0000-4000-8000-000000000093',
          name: 'TRL',
          value: 4,
          raw: 'TRL 4',
          max: 9,
          is_trl: true,
          order: 3,
        },
        {
          key: 'summarisation',
          definition_id: '00000000-0000-4000-8000-000000000094',
          name: 'Summarisation',
          value: null,
          raw: 'Researchers developed Backline, a high-throughput framework...',
          max: 100,
          is_trl: false,
          order: 4,
        },
        {
          key: 'empty_extraction',
          definition_id: '00000000-0000-4000-8000-000000000095',
          name: 'Unscored Extraction',
          value: null,
          raw: '—',
          max: 100,
          is_trl: false,
          order: 5,
        },
        {
          key: 'zero_dimension',
          definition_id: '00000000-0000-4000-8000-000000000096',
          name: 'Zero Metric',
          value: 0,
          raw: '0',
          max: 100,
          is_trl: false,
          order: 6,
        },
      ],
    })

    const out = renderToStaticMarkup(<ScoreRail paper={paperWithScreenshotScenario} t={t} />)

    // 1. Valid metrics ARE rendered on the bars list, each as a whole number
    expect(out).toContain('Research Metric')
    expect(out).toContain('59')
    expect(out).not.toContain('58.67')
    expect(out).toContain('Schwarz Fit')
    expect(out).toContain('27')
    expect(out).toContain('TRL')
    expect(out).toContain('4')

    // 2. Score of 0 IS rendered ("nie 0 ale niczego do wyswietlania") — a real
    // zero is a number, and rounding to whole numbers leaves it a figure, not
    // the dash a failed formula gets at the seam.
    expect(out).toContain('Zero Metric')
    expect(out).toContain('href="#dimension-zero_dimension"')
    expect(out).toMatch(/dark:text-white">0<\/span>/)

    // 3. Summarisation and empty unscored extractions MUST NOT be rendered anywhere in ScoreRail
    expect(out).not.toContain('Summarisation')
    expect(out).not.toContain('href="#dimension-summarisation"')
    expect(out).not.toContain('Unscored Extraction')
    expect(out).not.toContain('href="#dimension-empty_extraction"')

    // 4. Radar chart exists and contains the valid dimensions including 0, but NOT Summarisation
    expect(out).toContain('data-row="radar"')
    expect(out).not.toContain('label="Summarisation"')
  })

  test('wraps bars and radar in collapsible details row with console-open hidden class', () => {
    const paper = mockPaper()
    const out = renderToStaticMarkup(<ScoreRail paper={paper} t={t} />)
    expect(out).toContain('data-row="details"')
    expect(out).toContain('group-has-[[data-console-open]]/record:hidden')
  })
})

import { makeT } from '@/lib/i18n'
import type { ScoredPaper } from '@/lib/papers/types'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { ScoreRail } from './score-rail'

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
  test('renders formatted Schwarz score and label', () => {
    const paper = mockPaper({ signal_score: 84.6 })
    const out = renderToStaticMarkup(<ScoreRail paper={paper} t={t} />)
    expect(out).toContain('84.6')
    expect(out).toContain('Schwarz Score')
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
    expect(out).toContain('Fit Score')
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

  test('renders scoring formula disclosure when signal_score_details contains code_snippet', () => {
    const paper = mockPaper({
      signal_score_details: {
        code_snippet: '0.6 * trl_level + 0.4 * fit_score',
        variables: { trl_level: 4, fit_score: 92 },
        calculated_at: '2026-09-08T22:00:00Z',
        error: null,
      },
    })
    const out = renderToStaticMarkup(<ScoreRail paper={paper} t={t} />)
    expect(out).toContain('data-row="formula"')
    expect(out).toContain('Scoring formula')
    expect(out).toContain('0.6 * trl_level + 0.4 * fit_score')
    expect(out).toContain('trl_level:')
    expect(out).toContain('fit_score:')
  })

  test('omits scoring formula disclosure when signal_score_details is null or lacks code_snippet', () => {
    const paperNoDetails = mockPaper({ signal_score_details: null })
    const outNoDetails = renderToStaticMarkup(<ScoreRail paper={paperNoDetails} t={t} />)
    expect(outNoDetails).not.toContain('data-row="formula"')

    const paperEmptySnippet = mockPaper({
      signal_score_details: {
        code_snippet: '',
        variables: {},
        calculated_at: '2026-09-08T22:00:00Z',
        error: null,
      },
    })
    const outEmptySnippet = renderToStaticMarkup(<ScoreRail paper={paperEmptySnippet} t={t} />)
    expect(outEmptySnippet).not.toContain('data-row="formula"')
  })
})

import { makeT } from '@/lib/i18n'
import type { Dimension, DimensionFacet, ScoredPaper } from '@/lib/papers/types'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { railEntries, ScoreRail } from './score-rail'

const t = makeT('en')

/**
 * Research Metrics as prod sends it (9 Sep 2026 scorecard): a headline, three
 * facets, and the same three as dict-shaped texts carrying the score again.
 */
function researchMetrics(
  scores: Record<'rigour' | 'novelty' | 'significance', number | null> = {
    rigour: 72,
    novelty: 68,
    significance: 67,
  },
): Dimension {
  const names = { rigour: 'Rigour', novelty: 'Novelty', significance: 'Significance' } as const
  const facets: DimensionFacet[] = (Object.keys(names) as (keyof typeof names)[]).map((k) => ({
    key: `${k}_score`,
    name: names[k],
    value: scores[k],
    max: 100,
    text: null,
    band: null,
  }))
  return {
    key: 'research_metrics',
    definition_id: '00000000-0000-4000-8000-000000000014',
    name: 'Research Metrics',
    value: 68,
    raw: '68',
    max: 100,
    is_trl: false,
    facets,
    texts: (Object.keys(names) as (keyof typeof names)[]).map((k) => ({
      key: k,
      name: names[k],
      type: 'dict',
      is_dict: true,
      score: scores[k],
      value: `${names[k]} assessment prose.`,
      dict_value: { score: scores[k], insight: `${names[k]} assessment prose.` },
    })),
  }
}

/** Each bar in rail order: "label → anchor", and the figure its value cell prints. */
function bars(out: string): { link: string; figure: string }[] {
  return [
    ...out.matchAll(
      /<li data-row="bar"><a href="#([^"]+)"[^>]*><span class="truncate">([^<]*)<\/span>.*?<span class="text-right[^"]*">(.*?)<\/span><\/a>/g,
    ),
  ].map((m) => ({ link: `${m[2]} → ${m[1]}`, figure: m[3]!.replace(/<[^>]+>/g, '') }))
}
const barLabels = (out: string) => bars(out).map((b) => b.link)

/** The radar's axes as printed: the label and the figure under it, in axis order. */
function radarAxes(out: string): string[] {
  return [...out.matchAll(/<text [^>]*>(.*?)<\/text>/g)].map((m) => {
    const spans = [...m[1]!.matchAll(/<tspan[^>]*>([^<]*)<\/tspan>/g)].map((s) => s[1])
    return `${spans.slice(0, -1).join(' ')} ${spans.at(-1)}`
  })
}

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

  test('unpacks Research Metrics into one bar per sub-score, in place, linking to each row', () => {
    const paper = mockPaper({
      dimensions: [researchMetrics(), mockPaper().dimensions[0]!, mockPaper().dimensions[1]!],
    })
    const out = renderToStaticMarkup(<ScoreRail paper={paper} t={t} />)
    expect(barLabels(out)).toEqual([
      'Rigour → dimension-research_metrics-rigour_score',
      'Novelty → dimension-research_metrics-novelty_score',
      'Significance → dimension-research_metrics-significance_score',
      'Fit Score → dimension-fit_score',
      'TRL → dimension-trl_level',
    ])
    expect(out).not.toContain('Research Metrics')
    expect(out).not.toContain('href="#dimension-research_metrics"')
    // Each bar prints its own figure, not the headline's 68.
    expect(bars(out).map((b) => b.figure)).toEqual(['72', '68', '67', '92', '4/9'])
  })

  test('the first sub-score bar also answers for the article above the rows', () => {
    const entries = railEntries(mockPaper({ dimensions: [researchMetrics()] }))
    expect(entries.map((e) => e.watch)).toEqual([
      ['dimension-research_metrics'],
      undefined,
      undefined,
    ])
  })

  test('the radar draws the same five axes as the bars, printing the sub-score figures', () => {
    const paper = mockPaper({
      dimensions: [researchMetrics(), mockPaper().dimensions[0]!, mockPaper().dimensions[1]!],
    })
    const out = renderToStaticMarkup(<ScoreRail paper={paper} t={t} />)
    expect(radarAxes(out)).toEqual([
      'Rigour 72',
      'Novelty 68',
      'Significance 67',
      'Fit Score 92',
      'TRL 4',
    ])
  })

  test('keeps the single Research Metrics bar when the definition has fewer than two sub-scores', () => {
    const one = researchMetrics()
    one.facets = one.facets!.slice(0, 1)
    one.texts = one.texts!.slice(0, 1)
    const paper = mockPaper({ dimensions: [one, ...mockPaper().dimensions] })
    const out = renderToStaticMarkup(<ScoreRail paper={paper} t={t} />)
    expect(bars(out)[0]).toEqual({
      link: 'Research Metrics → dimension-research_metrics',
      figure: '68',
    })
    expect(out).not.toContain('dimension-research_metrics-rigour_score')
  })

  test('keeps the single bar when the sub-scores arrived as prose without figures', () => {
    const prose = researchMetrics({ rigour: null, novelty: null, significance: null })
    const paper = mockPaper({ dimensions: [prose, ...mockPaper().dimensions] })
    const out = renderToStaticMarkup(<ScoreRail paper={paper} t={t} />)
    expect(bars(out)[0]).toEqual({
      link: 'Research Metrics → dimension-research_metrics',
      figure: '68',
    })
    expect(radarAxes(out)).toHaveLength(4)
  })

  test('a single sub-score without a figure shows a dash and stays off the radar', () => {
    const paper = mockPaper({
      dimensions: [
        researchMetrics({ rigour: 72, novelty: null, significance: 67 }),
        ...mockPaper().dimensions,
      ],
    })
    const out = renderToStaticMarkup(<ScoreRail paper={paper} t={t} />)
    expect(bars(out).map((b) => b.figure)).toEqual(['72', '—', '67', '92', '4/9', '75'])
    expect(radarAxes(out).map((a) => a.split(' ')[0])).toEqual([
      'Rigour',
      'Significance',
      'Fit',
      'TRL',
      'Novelty',
    ])
    expect(railEntries(paper)[1]).toMatchObject({ label: 'Novelty', value: null, max: 100 })
  })

  test('leaves out the sub-score the column hides, so no bar links to a missing row', () => {
    // A definition the column reads as TRL by name hides a "Confidence" sub-score.
    const d = researchMetrics()
    d.name = 'Research Metrics (TRL)'
    d.facets!.push({
      key: 'confidence',
      name: 'Confidence',
      value: 90,
      max: 100,
      text: null,
      band: null,
    })
    const entries = railEntries(mockPaper({ dimensions: [d] }))
    expect(entries.map((e) => e.label)).toEqual(['Rigour', 'Novelty', 'Significance'])
  })

  test('trims a long sub-score name the way it trims a definition name', () => {
    const d = researchMetrics()
    d.facets![0]!.name = 'Rigour (methods & analysis)'
    d.texts![0]!.name = 'Rigour (methods & analysis)'
    expect(railEntries(mockPaper({ dimensions: [d] }))[0]!.label).toBe('Rigour')
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
})

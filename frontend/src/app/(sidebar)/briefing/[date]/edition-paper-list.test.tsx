import { ALL_ON } from '@/lib/features'
import { FeaturesTestProvider } from '@/lib/features-client'
import type { ScoredPaper } from '@/lib/papers/types'
import { StarsProvider } from '@/lib/stars-client'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { EditionPaperList } from './edition-paper-list'

function mockPaper(id: string, title: string, signalScore: number | null): ScoredPaper {
  return {
    id,
    workspace_id: '00000000-0000-4000-8000-000000000010',
    pipeline_run_id: '00000000-0000-4000-8000-000000000020',
    title,
    authors: ['Author One', 'Author Two'],
    authors_raw: 'Author One, Author Two',
    abstract: `Abstract describing ${title}`,
    doi: null,
    arxiv_id: `2609.${id.slice(-5)}`,
    source: 'arxiv',
    screening_status: 'accepted',
    screening_reasoning: 'Met all relevance criteria.',
    abstract_screening_reasoning: null,
    full_text_screening_reasoning: null,
    signal_score: signalScore,
    signal_score_details: null,
    dimensions: [
      {
        key: 'novelty',
        definition_id: '00000000-0000-4000-8000-000000000030',
        name: 'Novelty',
        value: 8.5,
        raw: '8.5',
        max: 10,
        is_trl: false,
      },
    ],
    pdf_key: null,
    markdown_key: null,
    source_url: `https://arxiv.org/abs/2609.${id.slice(-5)}`,
    is_benchmark: false,
    evaluation_label: null,
    published_date: '2026-09-08',
    created_at: '2026-09-09T08:00:00Z',
    pipeline_run_name: 'Agentic Scan',
    risk_and_affiliation: null,
  }
}

describe('EditionPaperList Component Rendering', () => {
  const paper1 = mockPaper('00000000-0000-4000-8000-000000000001', 'Quantum Neural Networks', 91.2)
  const paper2 = mockPaper('00000000-0000-4000-8000-000000000002', 'High-Throughput Inference', 82.0)
  const runId = '00000000-0000-4000-8000-000000000020'
  const logHref = '/briefing/2026-09-09/run'

  test('renders paper cards with runId query parameter in link', () => {
    const out = renderToStaticMarkup(
      <EditionPaperList papers={[paper1, paper2]} runId={runId} logHref={logHref} />,
    )

    // Check title presence
    expect(out).toContain('Quantum Neural Networks')
    expect(out).toContain('High-Throughput Inference')

    // Check card link contains ?run= parameter for reproducible scoring snapshot
    expect(out).toContain(`href="/papers/${paper1.id}?run=${runId}"`)
    expect(out).toContain(`href="/papers/${paper2.id}?run=${runId}"`)

    // Check paper count label
    expect(out).toContain('2 papers')

    // Check screening log link
    expect(out).toContain(`href="${logHref}"`)
    expect(out).toContain('Screening log →')
  })

  test('renders singular "1 paper" when only one paper is in briefing', () => {
    const out = renderToStaticMarkup(
      <EditionPaperList papers={[paper1]} runId={runId} logHref={logHref} />,
    )
    expect(out).toContain('1 paper')
    expect(out).not.toContain('1 papers')
    expect(out).toContain('Quantum Neural Networks')
  })

  test('renders empty state when briefing has 0 surfaced papers', () => {
    const out = renderToStaticMarkup(
      <EditionPaperList papers={[]} runId={runId} logHref={logHref} />,
    )
    expect(out).toContain('0 papers')
    expect(out).toContain('No papers are on file for this briefing.')
    expect(out).toContain(`href="${logHref}"`)
  })

  test('renders StarredChip when stars feature flag is enabled', () => {
    const out = renderToStaticMarkup(
      <FeaturesTestProvider features={{ ...ALL_ON, stars: true }}>
        <StarsProvider initial={{ papers: [paper1.id], briefings: [] }}>
          <EditionPaperList papers={[paper1, paper2]} runId={runId} logHref={logHref} />
        </StarsProvider>
      </FeaturesTestProvider>,
    )
    expect(out).toContain('Starred')
    expect(out).toContain('1') // count of starred papers
  })

  test('omits StarredChip when stars feature flag is disabled', () => {
    const out = renderToStaticMarkup(
      <FeaturesTestProvider features={{ ...ALL_ON, stars: false }}>
        <StarsProvider initial={{ papers: [paper1.id], briefings: [] }}>
          <EditionPaperList papers={[paper1, paper2]} runId={runId} logHref={logHref} />
        </StarsProvider>
      </FeaturesTestProvider>,
    )
    expect(out).not.toContain('Starred')
  })
})

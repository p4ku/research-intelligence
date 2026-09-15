import { ALL_ON } from '@/lib/features'
import { FeaturesTestProvider } from '@/lib/features-client'
import { SCORE_STEP } from '@/lib/papers/score'
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
  const paper2 = mockPaper(
    '00000000-0000-4000-8000-000000000002',
    'High-Throughput Inference',
    82.0,
  )
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

  // The stakeholder's edit of 10 Sep 2026: the score filter said "Any" twice
  // (the group's header and the slider's own readout) and moved in fives.
  test('the score filter reads as a figure, never "Any", and steps by one', () => {
    const out = renderToStaticMarkup(
      <EditionPaperList papers={[paper1, paper2]} runId={runId} logHref={logHref} />,
    )
    // Not a substring test: "Any score" names the track's low end and stays.
    expect(out).not.toMatch(/>Any</)
    expect(out).toContain('Any score')
    expect(out).toContain('Only the strongest')
    // The readout is the floor itself, 0 while the whole edition is shown.
    expect(out).toMatch(/tabular-nums[^"]*"[^>]*>0</)
    expect(out).toContain(`step="${SCORE_STEP}"`)
    expect(SCORE_STEP).toBe(1)
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

describe('EditionPaperList paging', () => {
  const runId = '00000000-0000-4000-8000-000000000020'
  const logHref = '/briefing/2026-09-09/run'
  const many = Array.from({ length: 45 }, (_, i) =>
    mockPaper(
      `00000000-0000-4000-8000-0000000${String(i + 1).padStart(5, '0')}`,
      `Paper ${i + 1}`,
      100 - i,
    ),
  )

  test('a briefing that fits on one page has no pager and the plain count', () => {
    const out = renderToStaticMarkup(
      <EditionPaperList papers={many.slice(0, 20)} runId={runId} logHref={logHref} />,
    )
    expect(out).toContain('20 papers')
    expect(out).not.toContain('aria-label="Pagination"')
  })

  test('a large briefing mounts the first twenty cards, the range and the pager', () => {
    const out = renderToStaticMarkup(
      <EditionPaperList papers={many} runId={runId} logHref={logHref} />,
    )
    expect(out).toContain('1–20 of 45 papers')
    expect(out).toContain('Paper 1</h3>')
    expect(out).toContain('Paper 20</h3>')
    expect(out).not.toContain('Paper 21</h3>')
    expect(out).toContain('aria-label="Pagination"')
    expect(out).toContain('aria-current="page"')
    expect(out).toContain('Previous')
    expect(out).toContain('Next')
  })

  test('the gallery (no router) still pages from its local view', () => {
    const out = renderToStaticMarkup(
      <EditionPaperList papers={many} runId={runId} logHref={logHref} syncUrl={false} />,
    )
    expect(out).toContain('1–20 of 45 papers')
  })

  test('server-side pagination with total passed builds paginator for full count', () => {
    const out = renderToStaticMarkup(
      <EditionPaperList
        papers={many.slice(0, 20)}
        runId={runId}
        logHref={logHref}
        total={473}
        page={1}
        pageSize={20}
      />,
    )
    expect(out).toContain('1–20 of 473 papers')
    expect(out).toContain('Paper 1</h3>')
    expect(out).toContain('Paper 20</h3>')
    expect(out).toContain('aria-label="Pagination"')
    expect(out).toContain('aria-current="page"')
    expect(out).toContain('Previous')
    expect(out).toContain('Next')
  })
})

import { ALL_ON } from '@/lib/features'
import { FeaturesTestProvider } from '@/lib/features-client'
import { makeT } from '@/lib/i18n'
import type { ScoredPaper } from '@/lib/papers/types'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { PaperHeader, PaperHeaderSkeleton } from './paper-header'

const t = makeT('en')

function samplePaper(overrides: Partial<ScoredPaper> = {}): ScoredPaper {
  return {
    id: '00000000-0000-4000-8000-000000000041',
    workspace_id: '00000000-0000-4000-8000-000000000001',
    pipeline_run_id: '00000000-0000-4000-8000-000000000031',
    title: 'Dynamic Intermediate Representation for Hybrid Quantum-Classical Programs',
    authors: ['Alex Rice', 'Chris Heunen', 'Tobias Grosser'],
    authors_raw: 'Alex Rice, Chris Heunen, Tobias Grosser',
    abstract: 'Quantum compilers typically follow the circuit model.',
    doi: '10.1145/3611643.3616281',
    arxiv_id: '2609.01037',
    source: 'arxiv',
    screening_status: 'full_text_passed',
    screening_reasoning:
      'Proposes an intermediate representation directly addressing hybrid quantum workflows.',
    abstract_screening_reasoning: null,
    full_text_screening_reasoning: null,
    signal_score: 84.6,
    signal_score_details: null,
    dimensions: [],
    pdf_key: null,
    markdown_key: null,
    source_url: 'https://arxiv.org/abs/2609.01037',
    is_benchmark: false,
    evaluation_label: null,
    published_date: '2026-09-01',
    created_at: '2026-09-08T22:00:00Z',
    pipeline_run_name: 'Hybrid AI Quantum Scan',
    risk_and_affiliation: {
      affiliations: ['University of Edinburgh', 'TU Munich'],
      author_contacts: ['alex.rice@ed.ac.uk'],
      funding_entities: ['European Research Council (ERC)'],
      codebase_artifact_link: 'https://github.com/hybrid-quantum/dynamic-ir',
      flags: [
        {
          key: 'gdpr',
          label: 'GDPR Sovereignty',
          value: 'Compliant',
          status: 'safe',
        },
      ],
    },
    ...overrides,
  }
}

describe('PaperHeader Component Rendering', () => {
  test('renders title, author list, source, and published date', () => {
    const paper = samplePaper()
    const out = renderToStaticMarkup(<PaperHeader paper={paper} t={t} lang="en" />)

    expect(out).toContain(
      'Dynamic Intermediate Representation for Hybrid Quantum-Classical Programs',
    )
    expect(out).toContain('Alex Rice, Chris Heunen, Tobias Grosser')
    expect(out).toContain('arxiv')
    expect(out).toContain('Published')
  })

  test('renders formatted arXiv ID and external link to original paper', () => {
    const paper = samplePaper()
    const out = renderToStaticMarkup(<PaperHeader paper={paper} t={t} lang="en" />)

    expect(out).toContain('arXiv:2609.01037')
    expect(out).toContain('href="https://arxiv.org/abs/2609.01037"')
    expect(out).toContain('View original paper')
  })

  test('embeds RiskAffiliationFlagging card directly in masthead', () => {
    const paper = samplePaper()
    const out = renderToStaticMarkup(<PaperHeader paper={paper} t={t} lang="en" />)

    expect(out).toContain('University of Edinburgh · TU Munich')
    expect(out).toContain('href="mailto:alex.rice@ed.ac.uk"')
    expect(out).toContain('https://github.com/hybrid-quantum/dynamic-ir')
    expect(out).toContain('GDPR Sovereignty:')
  })

  test('renders star toggle when stars feature flag is enabled', () => {
    const paper = samplePaper()
    const out = renderToStaticMarkup(
      <FeaturesTestProvider features={{ ...ALL_ON, stars: true }}>
        <PaperHeader paper={paper} t={t} lang="en" />
      </FeaturesTestProvider>,
    )

    expect(out).toContain('aria-label="Star this paper"')
  })

  test('omits star toggle when stars feature flag is disabled', () => {
    const paper = samplePaper()
    const out = renderToStaticMarkup(
      <FeaturesTestProvider features={{ ...ALL_ON, stars: false }}>
        <PaperHeader paper={paper} t={t} lang="en" features={{ ...ALL_ON, stars: false }} />
      </FeaturesTestProvider>,
    )

    expect(out).not.toContain('aria-label="Star this paper"')
  })

  test('renders Benchmark Control badge when is_benchmark is true with evaluation_label', () => {
    const paper = samplePaper({ is_benchmark: true, evaluation_label: 'passed' })
    const out = renderToStaticMarkup(<PaperHeader paper={paper} t={t} lang="en" />)

    expect(out).toContain('data-row="benchmark-control"')
    expect(out).toContain('Benchmark Control (Passed)')
  })

  test('renders Benchmark Control badge without evaluation_label', () => {
    const paper = samplePaper({ is_benchmark: true, evaluation_label: null })
    const out = renderToStaticMarkup(<PaperHeader paper={paper} t={t} lang="en" />)

    expect(out).toContain('data-row="benchmark-control"')
    expect(out).toContain('Benchmark Control')
    expect(out).not.toContain('(Passed)')
  })

  test('PaperHeaderSkeleton renders matching structure in skeleton state', () => {
    const out = renderToStaticMarkup(<PaperHeaderSkeleton />)

    expect(out).toContain('data-shape="paper-header"')
    expect(out).toContain('data-state="skeleton"')
    expect(out).toContain('data-row="meta"')
    expect(out).toContain('data-row="title"')
    expect(out).toContain('data-row="authors"')
  })
})

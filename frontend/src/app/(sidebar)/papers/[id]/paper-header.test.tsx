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
    expect(out).not.toContain('Full text passed')
  })

  test('omits arXiv identifier at the top and renders external link to original paper', () => {
    const paper = samplePaper()
    const out = renderToStaticMarkup(<PaperHeader paper={paper} t={t} lang="en" />)

    // arXiv identifier badge is removed to prevent design mismatch with sources like OpenAlex
    expect(out).not.toContain('arXiv:2609.01037')
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

  test('renders title with responsive wrapping classes and without artificial 30ch clamp', () => {
    const paper = samplePaper()
    const out = renderToStaticMarkup(<PaperHeader paper={paper} t={t} lang="en" />)

    expect(out).toContain('data-row="title"')
    expect(out).not.toContain('max-w-[30ch]')
    expect(out).toContain('text-pretty')
    expect(out).toContain('break-words')
  })

  test('renders PaperHeader with production extraction 0ee3ad96-c128-4aa0-a4f8-0a6ee644659d', () => {
    // Exact paper payload corresponding to extraction 0ee3ad96-c128-4aa0-a4f8-0a6ee644659d
    const paper = samplePaper({
      title: 'MQT Core: A Physical and Logical Quantum Circuit Design Automation Framework',
      authors: ['Lukas Berent', 'Robert Wille'],
      authors_raw: 'Lukas Berent, Robert Wille',
      risk_and_affiliation: {
        affiliations: [
          'Technical University of Munich, Germany',
          'Munich Quantum Valley, Germany',
          'Software Competence Center Hagenberg GmbH, Austria',
        ],
        author_contacts: ['lukas.berent@tum.de', 'robert.wille@tum.de'],
        funding_entities: [
          'European Research Council (ERC)',
          'Bavarian State Ministry of Science and Arts',
          'Federal Ministry of Education and Research (BMBF)',
        ],
        codebase_artifact_link: 'https://github.com/cda-tum/mqt-core',
        schwarz_ecosystem_affiliation: 'YES (TUM)',
        gdpr_concerns: 'NO',
        competitor_involvement: 'None',
        flags: [
          {
            key: 'gdpr',
            label: 'GDPR Sovereignty',
            value: 'NO',
            status: 'safe',
          },
          {
            key: 'schwarz_ecosystem',
            label: 'Schwarz Ecosystem',
            value: 'YES (TUM)',
            status: 'highlight',
          },
          {
            key: 'competitor',
            label: 'Competitor Involvement',
            value: 'None',
            status: 'safe',
          },
        ],
      },
    })

    const out = renderToStaticMarkup(<PaperHeader paper={paper} t={t} lang="en" />)

    // Authors line
    expect(out).toContain('data-row="authors"')
    expect(out).toContain('Lukas Berent, Robert Wille')

    // Affiliations under authors
    expect(out).toContain(
      'Technical University of Munich, Germany · Munich Quantum Valley, Germany · Software Competence Center Hagenberg GmbH, Austria',
    )

    // Mailto contacts
    expect(out).toContain('href="mailto:lukas.berent@tum.de"')
    expect(out).toContain('href="mailto:robert.wille@tum.de"')

    // Artifact Repository
    expect(out).toContain('href="https://github.com/cda-tum/mqt-core"')
    expect(out).toContain('Artifact Repository')

    // Funding entities
    expect(out).toContain('Funding:')
    expect(out).toContain(
      'European Research Council (ERC); Bavarian State Ministry of Science and Arts; Federal Ministry of Education and Research (BMBF)',
    )

    // Flags
    expect(out).toContain('GDPR Sovereignty')
    expect(out).toContain('Schwarz Ecosystem')
    expect(out).toContain('YES (TUM)')
  })

  test('does not render risk and affiliation container when risk_and_affiliation is null', () => {
    const paper = samplePaper({ risk_and_affiliation: null })
    const out = renderToStaticMarkup(<PaperHeader paper={paper} t={t} lang="en" />)
    expect(out).toContain('data-row="authors"')
    expect(out).not.toContain('data-row="risk-and-affiliation"')
  })

  test('does not render risk and affiliation container when risk_and_affiliation is undefined', () => {
    const paper = samplePaper({ risk_and_affiliation: undefined })
    const out = renderToStaticMarkup(<PaperHeader paper={paper} t={t} lang="en" />)
    expect(out).toContain('data-row="authors"')
    expect(out).not.toContain('data-row="risk-and-affiliation"')
  })

  test('does not render risk and affiliation container when risk_and_affiliation has all empty fields', () => {
    const paper = samplePaper({
      risk_and_affiliation: {
        affiliations: [],
        author_contacts: [],
        funding_entities: [],
        codebase_artifact_link: null,
        flags: [],
      },
    })
    const out = renderToStaticMarkup(<PaperHeader paper={paper} t={t} lang="en" />)
    expect(out).toContain('data-row="authors"')
    expect(out).not.toContain('data-row="risk-and-affiliation"')
  })
})

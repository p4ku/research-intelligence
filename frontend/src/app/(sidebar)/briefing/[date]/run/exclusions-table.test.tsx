import type { EditionExclusion } from '@/lib/bff/briefings/schema'
import { makeT } from '@/lib/i18n'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { ExclusionsTable, ExclusionsTableSkeleton } from './exclusions-table'

const t = makeT('en')

const sampleExclusions: EditionExclusion[] = [
  {
    paper_id: '00000000-0000-4000-8000-000000000101',
    title: 'Band Structure Modulation of ZrO2 Nanoparticles',
    source: 'arxiv',
    reason: 'Classical chemistry study not relating to quantum accelerators.',
    published_date: '2026-09-08',
    source_url: 'https://arxiv.org/abs/2609.00101',
  },
  {
    paper_id: '00000000-0000-4000-8000-000000000102',
    title: 'Statistical Symmetry Release for Equivariant Quantum Learning',
    source: 'openalex',
    reason: null,
    published_date: null,
    source_url: null,
  },
]

describe('ExclusionsTable Component Rendering', () => {
  test('renders paper title as internal link with run query parameter', () => {
    const html = renderToStaticMarkup(
      <ExclusionsTable
        exclusions={sampleExclusions}
        t={t}
        runId="7246bc6a-85cf-423a-8d0c-53eb4c8f9bd9"
        lang="en"
      />,
    )

    expect(html).toContain(
      'href="/papers/00000000-0000-4000-8000-000000000101?run=7246bc6a-85cf-423a-8d0c-53eb4c8f9bd9"',
    )
    expect(html).toContain('Band Structure Modulation of ZrO2 Nanoparticles')
  })

  test('renders source metadata including published date and external link to original paper', () => {
    const html = renderToStaticMarkup(
      <ExclusionsTable
        exclusions={sampleExclusions}
        t={t}
        runId="7246bc6a-85cf-423a-8d0c-53eb4c8f9bd9"
        lang="en"
      />,
    )

    // Row 1: has published date and external link
    expect(html).toContain('arxiv')
    expect(html).toContain('Published Sep 8, 2026')
    expect(html).toContain('href="https://arxiv.org/abs/2609.00101"')
    expect(html).toContain('target="_blank"')
    expect(html).toContain('rel="noreferrer"')
    expect(html).toContain('View original paper')

    // Row 2: lacks published date and external link, but renders source and fallback dash
    expect(html).toContain('openalex')
    expect(html).toContain('—')
  })

  test('renders paper link without runId when runId is not supplied', () => {
    const html = renderToStaticMarkup(<ExclusionsTable exclusions={sampleExclusions} t={t} />)

    expect(html).toContain('href="/papers/00000000-0000-4000-8000-000000000101"')
    expect(html).not.toContain('?run=')
  })

  test('renders ExclusionsTableSkeleton with matching columns', () => {
    const html = renderToStaticMarkup(<ExclusionsTableSkeleton t={t} rows={3} />)

    expect(html).toContain('data-shape="exclusions-table"')
    expect(html).toContain('data-state="skeleton"')
    expect(html).toContain('Paper')
    expect(html).toContain('Source')
    expect(html).toContain('Why it did not pass')
  })
})

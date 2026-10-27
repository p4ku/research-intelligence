import { mockPrismaMetrics } from '@/lib/bff/slr/fixtures'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { PrismaFlowDiagram } from './prisma-flow-diagram'

describe('PrismaFlowDiagram Component Rendering', () => {
  test('renders all 4 PRISMA 2020 tiers with attrition statistics', () => {
    const html = renderToStaticMarkup(<PrismaFlowDiagram metrics={mockPrismaMetrics} />)

    // Stage 1: Identification
    expect(html).toContain('Identification')
    expect(html).toContain('480')
    expect(html).toContain('PUBMED')
    expect(html).toContain('− 42') // Duplicates removed

    // Stage 2: Screening
    expect(html).toContain('Screening (Title &amp; Abstract)')
    expect(html).toContain('438')
    expect(html).toContain('− 320')
    expect(html).toContain('Wrong Pathogen / Topic')

    // Stage 3: Eligibility
    expect(html).toContain('Eligibility (Full-Text Appraisal)')
    expect(html).toContain('118')
    expect(html).toContain('− 86')
    expect(html).toContain('Absent Empirical Methodology')

    // Stage 4: Included Studies
    expect(html).toContain('Included Studies')
    expect(html).toContain('32')
    expect(html).toContain('24')
    expect(html).toContain('View Included Studies (32)')
    expect(html).toContain('/slr/studies')
    expect(html).toContain('/audit-queue')
  })

  test('propagates runId to studies and briefing action links', () => {
    const html = renderToStaticMarkup(
      <PrismaFlowDiagram metrics={mockPrismaMetrics} runId="run-12345" />,
    )

    expect(html).toContain('/slr/studies?runId=run-12345')
    expect(html).toContain('/briefing?runId=run-12345')
  })

  test('renders clean empty state fallback when metrics is null', () => {
    const html = renderToStaticMarkup(<PrismaFlowDiagram metrics={null} />)
    expect(html).toContain('No PRISMA flow metrics available')
  })
})

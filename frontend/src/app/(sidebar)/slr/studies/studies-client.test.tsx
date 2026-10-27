import { mockPrismaMetrics, mockRobAssessments, mockSLRRuns } from '@/lib/bff/slr/fixtures'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { SLRStudiesClient } from './studies-client'

describe('SLRStudiesClient Component Rendering', () => {
  test('renders top breadcrumb, KPI stats and studies table', () => {
    const html = renderToStaticMarkup(
      <SLRStudiesClient
        initialRuns={mockSLRRuns}
        initialMetrics={mockPrismaMetrics}
        initialRob={mockRobAssessments}
        initialRunId={mockSLRRuns[0].id}
      />,
    )

    // Breadcrumb and headings
    expect(html).toContain('Included Studies (PRISMA Stage 4)')
    expect(html).toContain('SLR Review &amp; Quality Console')

    // KPI cards
    expect(html).toContain('Studies in Synthesis:')
    expect(html).toContain('Quantitative Meta-Analysis:')
    expect(html).toContain('Low Risk of Bias:')

    // Table content
    expect(html).toContain('Attention Is All You Need in Clinical Prognosis')
    expect(html).toContain('Evaluating Diffusion Transformers on Retrospective Cohorts')
    expect(html).toContain('Export Studies (CSV)')
  })

  test('renders clean empty state fallback when no studies are admitted', () => {
    const html = renderToStaticMarkup(
      <SLRStudiesClient
        initialRuns={mockSLRRuns}
        initialMetrics={null}
        initialRob={[]}
        initialRunId={mockSLRRuns[0].id}
      />,
    )

    expect(html).toContain('No studies admitted yet for this pipeline run.')
    expect(html).toContain('0 Verified Admitted')
  })
})

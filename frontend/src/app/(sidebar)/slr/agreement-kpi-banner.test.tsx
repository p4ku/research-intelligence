import { mockPrismaMetrics } from '@/lib/bff/slr/fixtures'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { AgreementKpiBanner } from './agreement-kpi-banner'

describe('AgreementKpiBanner Component Rendering', () => {
  test('renders all 4 statistical KPI metric cards with mock data', () => {
    const html = renderToStaticMarkup(<AgreementKpiBanner metrics={mockPrismaMetrics} />)

    // Human Kappa
    expect(html).toContain('Inter-Rater Reliability')
    expect(html).toContain('κ = 0.88')
    expect(html).toContain('Almost Perfect')

    // AI vs Human
    expect(html).toContain('AI vs. Human Concordance')
    expect(html).toContain('κ = 0.84')

    // Sensitivity & Specificity
    expect(html).toContain('AI Sensitivity (Recall)')
    expect(html).toContain('96.5%')
    expect(html).toContain('AI Specificity')
    expect(html).toContain('92.3%')
  })

  test('gracefully handles null metrics with fallback badges', () => {
    const html = renderToStaticMarkup(<AgreementKpiBanner metrics={null} />)

    expect(html).toContain('Dual Audit In Progress')
    expect(html).toContain('N/A')
  })

  test('accurately classifies kappa thresholds', () => {
    const moderateMetrics = {
      ...mockPrismaMetrics,
      human_inter_rater_kappa: 0.52,
    }
    const html = renderToStaticMarkup(<AgreementKpiBanner metrics={moderateMetrics} />)
    expect(html).toContain('Moderate Agreement')
    expect(html).toContain('κ = 0.52')
  })
})

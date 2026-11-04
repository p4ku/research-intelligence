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

  test('maps D1_randomization..D5_selection and ROBINS-I domain keys and counts critical_risk in High Risk', () => {
    const robWithRobinsAndCritical = [
      ...mockRobAssessments,
      {
        id: 'rob-004',
        paper: 'p-004',
        paper_title: 'Observational Cohort Study with ROBINS-I Critical Bias',
        pipeline_run: mockSLRRuns[0].id,
        framework: 'robins_i',
        domain_scores: {
          D1_confounding: { rating: 'critical_risk', quote: 'Uncontrolled confounding.', page: 2 },
          D2_selection: { rating: 'low_risk', quote: 'Consecutive enrollment.', page: 3 },
          D5_missing_data: { rating: 'some_concerns', quote: '12% loss to follow-up.', page: 5 },
          D6_measurement: { rating: 'low_risk', quote: 'Registry linkage.', page: 6 },
          D7_reporting: { rating: 'low_risk', quote: 'Protocol pre-registered.', page: 8 },
        },
        overall_bias: 'critical_risk',
        traffic_light_color: 'red',
        is_human_verified: false,
        human_notes: null,
      },
    ]

    const html = renderToStaticMarkup(
      <SLRStudiesClient
        initialRuns={mockSLRRuns}
        initialMetrics={mockPrismaMetrics}
        initialRob={robWithRobinsAndCritical}
        initialRunId={mockSLRRuns[0].id}
      />,
    )

    // RoB 2 domain tooltips should resolve D1_randomization -> low_risk instead of unclear
    expect(html).toContain('D1: Randomization process (low_risk)')
    // ROBINS-I domain tooltips should resolve D1_confounding -> critical_risk
    expect(html).toContain('D1: Bias due to confounding (critical_risk)')
    // High Risk filter pill should include both high_risk (1) and critical_risk (1) = 2
    expect(html).toContain('High Risk (2)')
  })
})

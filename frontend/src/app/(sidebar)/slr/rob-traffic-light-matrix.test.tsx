import { mockRobAssessments } from '@/lib/bff/slr/fixtures'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { RobTrafficLightMatrix } from './rob-traffic-light-matrix'

describe('RobTrafficLightMatrix Component Rendering', () => {
  test('renders traffic light matrix table with domains and bias assessments', () => {
    const html = renderToStaticMarkup(<RobTrafficLightMatrix assessments={mockRobAssessments} />)

    // Table headers & domains
    expect(html).toContain('Cochrane Risk of Bias (RoB 2) Traffic Light Matrix')
    expect(html).toContain('D1 Rand')
    expect(html).toContain('D2 Dev')
    expect(html).toContain('D3 Miss')
    expect(html).toContain('D4 Meas')
    expect(html).toContain('D5 Sel')
    expect(html).toContain('Overall Bias')

    // Studies
    expect(html).toContain('Attention Is All You Need in Clinical Prognosis')
    expect(html).toContain('Evaluating Diffusion Transformers on Retrospective Cohorts')
    expect(html).toContain('Uncalibrated Neural Estimators in Emergency Triage')

    // Overall badges
    expect(html).toContain('Low Risk')
    expect(html).toContain('Some Concerns')
    expect(html).toContain('High Risk')

    // Verification flags
    expect(html).toContain('✓ Verified')
  })

  test('renders graceful empty state when assessments list is empty', () => {
    const html = renderToStaticMarkup(<RobTrafficLightMatrix assessments={[]} />)
    expect(html).toContain('No Risk of Bias appraisals generated yet')
  })

  test('resolves ROBINS-I domain keys (D1_confounding..D7_reporting) into traffic light dots', () => {
    const robinsStudy = [
      {
        id: 'rob-robins-1',
        paper: 'p-robins-1',
        paper_title: 'Non-Randomized Observational Intervention Study',
        pipeline_run: 'a2a44548-6af3-47ce-a538-724427e69e0b',
        framework: 'robins_i',
        domain_scores: {
          D1_confounding: { rating: 'low_risk', quote: 'Propensity score matched.', page: 3 },
          D2_selection: { rating: 'low_risk', quote: 'All eligible patients included.', page: 4 },
          D5_missing_data: { rating: 'low_risk', quote: 'No missing data.', page: 5 },
          D6_measurement: { rating: 'low_risk', quote: 'Objective lab outcome.', page: 6 },
          D7_reporting: { rating: 'low_risk', quote: 'All outcomes reported.', page: 7 },
        },
        overall_bias: 'low_risk',
        traffic_light_color: 'green',
        is_human_verified: true,
        human_notes: 'Verified observational study.',
      },
    ]
    const html = renderToStaticMarkup(<RobTrafficLightMatrix assessments={robinsStudy} />)
    expect(html).toContain('Non-Randomized Observational Intervention Study')
    expect(html).toContain('Framework: ROBINS_I')
    expect(html).toContain('title="Low Risk of Bias"')
    expect(html).not.toContain('title="Unclear"')
  })
})

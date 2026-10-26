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
})

import { makeT } from '@/lib/i18n'
import type { Dimension } from '@/lib/papers/types'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { Assessment, definitionAnchor } from './assessment'

const t = makeT('en')

describe('Assessment Component Rendering', () => {
  const fullDimension: Dimension = {
    key: 'trl_level',
    definition_id: '00000000-0000-4000-8000-000000000011',
    name: 'TRL Level',
    value: 4,
    raw: 'TRL 4',
    max: 9,
    is_trl: true,
    has_postprocessing: true,
    band: 'TRL 4 — Technology validated in lab',
    rationale: 'Comprehensive benchmark evaluation across multiple simulator backends.',
    confidence: 0.92,
    model: 'google/gemini-3.8-flash',
    validation_status: 'valid',
    review_required: false,
    facets: [
      {
        key: 'confidence_score',
        name: 'Confidence score',
        value: 0.92,
        max: 1,
        text: 'Direct empirical results reported with standard deviations.',
      },
      {
        key: 'speedup_ratio',
        name: 'Speedup ratio',
        value: 2.4,
        max: 5,
        text: null,
      },
    ],
    texts: [
      {
        key: 'hardware_target_notes',
        name: 'Hardware target notes',
        value: 'Targeted at gate-model quantum processors with classical coprocessors.',
      },
    ],
    lists: [
      {
        key: 'core_contributions',
        name: 'Core contributions',
        items: [
          'Dynamic gate creation as first-class SSA values',
          'Hybrid loop-pipelining compiler optimization',
        ],
      },
    ],
    evidence: [
      '“Our intermediate representation reduces circuit compilation latency by 58%.”',
      '“Validated on 14 hybrid benchmark programs.”',
    ],
    facts: [
      { key: 'open_source', name: 'Open source', value: true },
      { key: 'quantum_backend', name: 'Quantum backend', value: 'Qiskit & Cirq' },
    ],
  }

  const riskDimension: Dimension = {
    key: 'risk_and_affiliation',
    definition_id: null,
    name: 'Risk and Affiliation',
    value: null,
    raw: '—',
    max: null,
    is_trl: false,
    is_risk_and_affiliation: true,
    rationale: 'Should not appear in Assessment list',
  }

  test('renders definition header, anchor id, band badge, and headline value', () => {
    const out = renderToStaticMarkup(<Assessment dimensions={[fullDimension]} t={t} />)
    const anchor = definitionAnchor(fullDimension)

    expect(out).toContain(`id="${anchor}"`)
    expect(out).toContain('TRL Level')
    expect(out).toContain('TRL 4 — Technology validated in lab')
    expect(out).toContain('4')
    expect(out).toContain('/9') // max is 9
  })

  test('renders rationale markdown prose', () => {
    const out = renderToStaticMarkup(<Assessment dimensions={[fullDimension]} t={t} />)
    expect(out).toContain('Comprehensive benchmark evaluation across multiple simulator backends.')
  })

  test('renders facets with progress fill and twin assessment notes', () => {
    const out = renderToStaticMarkup(<Assessment dimensions={[fullDimension]} t={t} />)
    expect(out).toContain('Confidence score')
    expect(out).toContain('0.92')
    expect(out).toContain('Direct empirical results reported with standard deviations.')
    expect(out).toContain('Speedup ratio')
    expect(out).toContain('2.4')
    // Facet progress scaleX
    expect(out).toContain('scaleX(')
  })

  test('renders titled texts sections', () => {
    const out = renderToStaticMarkup(<Assessment dimensions={[fullDimension]} t={t} />)
    expect(out).toContain('Hardware target notes')
    expect(out).toContain('Targeted at gate-model quantum processors with classical coprocessors.')
  })

  test('renders bulleted lists with item contents', () => {
    const out = renderToStaticMarkup(<Assessment dimensions={[fullDimension]} t={t} />)
    expect(out).toContain('Core contributions')
    expect(out).toContain('Dynamic gate creation as first-class SSA values')
    expect(out).toContain('Hybrid loop-pipelining compiler optimization')
  })

  test('renders evidence quotes unquoted within blockquote tags', () => {
    const out = renderToStaticMarkup(<Assessment dimensions={[fullDimension]} t={t} />)
    expect(out).toContain('<blockquote')
    expect(out).toContain('Our intermediate representation reduces circuit compilation latency by 58%.')
    expect(out).toContain('Validated on 14 hybrid benchmark programs.')
  })

  test('renders facts key-value pairs and converts booleans to Yes/No', () => {
    const out = renderToStaticMarkup(<Assessment dimensions={[fullDimension]} t={t} />)
    expect(out).toContain('Open source')
    expect(out).toContain('Yes')
    expect(out).toContain('Quantum backend')
    expect(out).toContain('Qiskit &amp; Cirq')
  })

  test('renders metadata: formatted confidence percentage and humanised model name', () => {
    const out = renderToStaticMarkup(<Assessment dimensions={[fullDimension]} t={t} />)
    expect(out).toContain('Confidence 92%')
    expect(out).toContain('Gemini 3.8 Flash')
  })

  test('shows review warning in metadata when review_required or validation_status is warn/fail', () => {
    const warnDim: Dimension = {
      ...fullDimension,
      key: 'novelty_check',
      name: 'Novelty Check',
      validation_status: 'warn',
    }
    const out = renderToStaticMarkup(<Assessment dimensions={[warnDim]} t={t} />)
    expect(out).toContain('Needs review')
  })

  test('filters out risk and affiliation dimensions from the Assessment article list', () => {
    const out = renderToStaticMarkup(<Assessment dimensions={[fullDimension, riskDimension]} t={t} />)
    expect(out).toContain('TRL Level')
    expect(out).not.toContain('Should not appear in Assessment list')
  })

  test('renders fallback copy when no visible dimensions are provided', () => {
    const out = renderToStaticMarkup(<Assessment dimensions={[]} t={t} />)
    expect(out).toContain('Not scored yet')
  })
})

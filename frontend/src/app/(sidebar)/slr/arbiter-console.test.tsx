import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { ArbiterConsole } from './arbiter-console'
import { mockDisputes } from '@/lib/bff/slr/fixtures'

describe('ArbiterConsole Component Rendering', () => {
  test('renders dispute lists, side-by-side comparison, and arbiter action form', () => {
    const html = renderToStaticMarkup(<ArbiterConsole disputes={mockDisputes} />)

    // Header & Tabs
    expect(html).toContain('Senior Arbiter Adjudication Console')
    expect(html).toContain('Pending (1)')
    expect(html).toContain('Resolved (1)')

    // Reviewer 1 vs Reviewer 2 vs AI
    expect(html).toContain('Reviewer 1')
    expect(html).toContain('Dr. Anna Kowalska')
    expect(html).toContain('Reviewer 2')
    expect(html).toContain('Dr. John Smith')
    expect(html).toContain('AI Agent Baseline')

    // Contested Paper Title
    expect(html).toContain('Mathematical Modeling of Zoonotic Spillover in Sub-Saharan Enclaves')

    // Arbiter Action Form
    expect(html).toContain('Senior Arbiter Binding Decision')
    expect(html).toContain('Admit Study (Include)')
    expect(html).toContain('Exclude Study')
    expect(html).toContain('Execute Binding Ruling')
  })

  test('renders resolved dispute with binding ruling and rationale', () => {
    const resolvedOnly = mockDisputes.filter((d) => d.status === 'resolved')
    const html = renderToStaticMarkup(<ArbiterConsole disputes={resolvedOnly} />)

    expect(html).toContain('Resolved (1)')
    expect(html).toContain('Genomic Surveillance of Multi-Drug Resistant Hospital Strains')
    expect(html).toContain('Binding Senior Arbiter ruling')
    expect(html).toContain('Resolved as EXCLUDE')
  })

  test('renders clean empty state when dispute list is empty', () => {
    const html = renderToStaticMarkup(<ArbiterConsole disputes={[]} />)
    expect(html).toContain('No reviewer disputes found')
  })
})

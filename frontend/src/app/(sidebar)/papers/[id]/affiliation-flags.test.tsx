import type { RiskAndAffiliation } from '@/lib/papers/types'
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import { RiskAffiliationFlagging } from './affiliation-flags'

describe('RiskAffiliationFlagging Component Rendering', () => {
  const fullRiskData: RiskAndAffiliation = {
    affiliations: ['University of Cambridge', 'Max Planck Institute'],
    author_contacts: ['lead.author@cam.ac.uk', 'pi@mpi.de'],
    funding_entities: ['DFG Grant #12345', 'Horizon Europe'],
    codebase_artifact_link: 'https://github.com/schwarz-research/quantum-ir',
    schwarz_ecosystem_affiliation: 'yes',
    gdpr_concerns: 'no',
    competitor_involvement: 'none',
    risk_score: 15,
    risk_score_assessment: 'Negligible risk',
    flags: [
      {
        key: 'gdpr',
        label: 'GDPR Sovereignty',
        value: 'Compliant (EU only)',
        status: 'safe',
      },
      {
        key: 'competitor',
        label: 'Competitor Involvement',
        value: 'High proprietary overlap',
        status: 'warn',
      },
      {
        key: 'schwarz_ecosystem',
        label: 'Schwarz Ecosystem',
        value: 'Aligned with STACKIT',
        status: 'highlight',
      },
      {
        key: 'export_control',
        label: 'Export Control',
        value: 'Dual-use check pending',
        status: 'neutral',
      },
    ],
  }

  test('renders affiliations list with separator', () => {
    const out = renderToStaticMarkup(<RiskAffiliationFlagging risk={fullRiskData} />)
    expect(out).toContain('University of Cambridge · Max Planck Institute')
  })

  test('renders author contacts with mailto links for email addresses', () => {
    const out = renderToStaticMarkup(<RiskAffiliationFlagging risk={fullRiskData} />)
    expect(out).toContain('href="mailto:lead.author@cam.ac.uk"')
    expect(out).toContain('href="mailto:pi@mpi.de"')
    expect(out).toContain('title="Email lead.author@cam.ac.uk"')
  })

  test('renders codebase artifact repository link with external target', () => {
    const out = renderToStaticMarkup(<RiskAffiliationFlagging risk={fullRiskData} />)
    expect(out).toContain('href="https://github.com/schwarz-research/quantum-ir"')
    expect(out).toContain('target="_blank"')
    expect(out).toContain('Artifact Repository')
  })

  test('renders funding entities with semicolon separator', () => {
    const out = renderToStaticMarkup(<RiskAffiliationFlagging risk={fullRiskData} />)
    expect(out).toContain('Funding: ')
    expect(out).toContain('DFG Grant #12345; Horizon Europe')
  })

  test('renders risk flags with matching status styling: safe (emerald), warn (amber), highlight (sky), neutral (zinc)', () => {
    const out = renderToStaticMarkup(<RiskAffiliationFlagging risk={fullRiskData} />)
    
    // Safe flag (emerald)
    expect(out).toContain('GDPR Sovereignty:')
    expect(out).toContain('Compliant (EU only)')
    expect(out).toContain('text-emerald-700')

    // Warn flag (amber)
    expect(out).toContain('Competitor Involvement:')
    expect(out).toContain('High proprietary overlap')
    expect(out).toContain('text-amber-800')

    // Highlight flag (sky)
    expect(out).toContain('Schwarz Ecosystem:')
    expect(out).toContain('Aligned with STACKIT')
    expect(out).toContain('text-sky-700')

    // Neutral flag (zinc)
    expect(out).toContain('Export Control:')
    expect(out).toContain('Dual-use check pending')
    expect(out).toContain('text-zinc-600')
  })

  test('renders risk score and assessment description', () => {
    const out = renderToStaticMarkup(<RiskAffiliationFlagging risk={fullRiskData} />)
    expect(out).toContain('Risk Score:')
    expect(out).toContain('15/100')
    expect(out).toContain('(Negligible risk)')
  })

  test('returns null when risk is undefined or null', () => {
    const out1 = renderToStaticMarkup(<RiskAffiliationFlagging risk={undefined} />)
    const out2 = renderToStaticMarkup(<RiskAffiliationFlagging risk={null} />)
    expect(out1).toBe('')
    expect(out2).toBe('')
  })

  test('returns null when risk data has all empty fields', () => {
    const emptyRisk: RiskAndAffiliation = {
      affiliations: [],
      author_contacts: [],
      funding_entities: [],
      flags: [],
      codebase_artifact_link: null,
    }
    const out = renderToStaticMarkup(<RiskAffiliationFlagging risk={emptyRisk} />)
    expect(out).toBe('')
  })
})

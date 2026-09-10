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

  test('renders risk flags with matching status styling and sorted in canonical order: Schwarz Ecosystem, Competitor Involvement, Compliance Risks', () => {
    const out = renderToStaticMarkup(<RiskAffiliationFlagging risk={fullRiskData} />)

    // Highlight flag (sky) - 1st
    expect(out).toContain('Schwarz Ecosystem:')
    expect(out).toContain('Aligned with STACKIT')
    expect(out).toContain('text-sky-700')

    // Warn flag (amber) - 2nd
    expect(out).toContain('Competitor Involvement:')
    expect(out).toContain('High proprietary overlap')
    expect(out).toContain('text-amber-800')

    // Safe flag (emerald) - 3rd (GDPR Sovereignty normalized to Compliance Risks)
    expect(out).toContain('Compliance Risks:')
    expect(out).toContain('Compliant (EU only)')
    expect(out).toContain('text-emerald-700')

    // Neutral flag (zinc) - 4th
    expect(out).toContain('Export Control:')
    expect(out).toContain('Dual-use check pending')
    expect(out).toContain('text-zinc-600')

    // Verify exact display order
    const ecoIdx = out.indexOf('Schwarz Ecosystem:')
    const compIdx = out.indexOf('Competitor Involvement:')
    const complianceIdx = out.indexOf('Compliance Risks:')
    expect(ecoIdx).toBeGreaterThan(-1)
    expect(compIdx).toBeGreaterThan(ecoIdx)
    expect(complianceIdx).toBeGreaterThan(compIdx)
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

  test('unpacks stringified JSON flags cleanly (Schwarz Ecosystem YES (TUM), Competitor None)', () => {
    const dictFlagsRisk: RiskAndAffiliation = {
      affiliations: [],
      author_contacts: [],
      funding_entities: [],
      flags: [
        {
          key: 'schwarz_ecosystem',
          label: 'Schwarz Ecosystem',
          value: JSON.stringify({ status: 'YES', matched_institutions: ['TUM'] }),
          status: 'neutral',
        },
        {
          key: 'competitor',
          label: 'Competitor Involvement',
          value: JSON.stringify({ status: 'NO', matches: null }),
          status: 'safe',
        },
      ],
      codebase_artifact_link: null,
    }
    const out = renderToStaticMarkup(<RiskAffiliationFlagging risk={dictFlagsRisk} />)
    expect(out).toContain('Schwarz Ecosystem:')
    expect(out).toContain('YES (TUM)')
    expect(out).toContain('text-sky-700')
    expect(out).toContain('Competitor Involvement:')
    expect(out).toContain('None')
    expect(out).toContain('text-emerald-700')
    expect(out).not.toContain('"status"')
  })

  test('preserves flag prose containing "None of the above" and apostrophes without regex corruption', () => {
    const customFlagRisk: RiskAndAffiliation = {
      affiliations: [],
      author_contacts: [],
      funding_entities: [],
      flags: [
        {
          key: 'compliance',
          label: 'Compliance Review',
          value:
            "The author's review concluded: None of the identified institutions are restricted.",
          status: 'safe',
        },
      ],
      codebase_artifact_link: null,
    }
    const out = renderToStaticMarkup(<RiskAffiliationFlagging risk={customFlagRisk} />)
    expect(out).toContain(
      'The author&#x27;s review concluded: None of the identified institutions are restricted.',
    )
    expect(out).not.toContain('null of the identified')
    expect(out).not.toContain('author"s')
  })

  test('unpacks direct dict_value flags with type: dict', () => {
    const directDictRisk: RiskAndAffiliation = {
      affiliations: [],
      author_contacts: [],
      funding_entities: [],
      flags: [
        {
          key: 'schwarz_ecosystem',
          label: 'Schwarz Ecosystem',
          value: 'YES (TUM)',
          status: 'highlight',
          type: 'dict',
          is_dict: true,
          dict_value: { status: 'YES', matched_institutions: ['TUM'] },
        },
        {
          key: 'competitor',
          label: 'Competitor Involvement',
          value: 'None',
          status: 'safe',
          type: 'dict',
          is_dict: true,
          dict_value: { status: 'NO', matches: null },
        },
      ],
      codebase_artifact_link: null,
    }
    const out = renderToStaticMarkup(<RiskAffiliationFlagging risk={directDictRisk} />)
    expect(out).toContain('Schwarz Ecosystem:')
    expect(out).toContain('YES (TUM)')
    expect(out).toContain('text-sky-700')
    expect(out).toContain('Competitor Involvement:')
    expect(out).toContain('None')
    expect(out).toContain('text-emerald-700')
  })

  test('renders production extraction 0ee3ad96-c128-4aa0-a4f8-0a6ee644659d payload into affiliations, contacts, funding, links, and flags', () => {
    // Live production extraction: https://sri.soinventive.co.uk/admin/research_intelligence/extraction/0ee3ad96-c128-4aa0-a4f8-0a6ee644659d/change/
    const liveRiskData: RiskAndAffiliation = {
      affiliations: [
        'Technical University of Munich, Germany',
        'Munich Quantum Valley, Germany',
        'Software Competence Center Hagenberg GmbH, Austria',
      ],
      author_contacts: ['lukas.berent@tum.de', 'robert.wille@tum.de'],
      funding_entities: [
        'European Research Council (ERC)',
        'Bavarian State Ministry of Science and Arts',
        'Federal Ministry of Education and Research (BMBF)',
      ],
      codebase_artifact_link: 'https://github.com/cda-tum/mqt-core',
      schwarz_ecosystem_affiliation: 'YES (TUM)',
      gdpr_concerns: 'NO',
      competitor_involvement: 'None',
      flags: [
        {
          key: 'gdpr',
          label: 'GDPR Sovereignty',
          value: 'NO',
          status: 'safe',
          type: 'dict',
          is_dict: true,
          dict_value: { status: 'NO', concerns: null },
        },
        {
          key: 'schwarz_ecosystem',
          label: 'Schwarz Ecosystem',
          value: 'YES (TUM)',
          status: 'highlight',
          type: 'dict',
          is_dict: true,
          dict_value: { status: 'YES', matched_institutions: ['TUM'] },
        },
        {
          key: 'competitor',
          label: 'Competitor Involvement',
          value: 'None',
          status: 'safe',
          type: 'dict',
          is_dict: true,
          dict_value: { status: 'NO', matches: null },
        },
      ],
    }

    const out = renderToStaticMarkup(<RiskAffiliationFlagging risk={liveRiskData} />)

    // 1. Affiliations
    expect(out).toContain(
      'Technical University of Munich, Germany · Munich Quantum Valley, Germany · Software Competence Center Hagenberg GmbH, Austria',
    )

    // 2. Author contacts mailto links
    expect(out).toContain('href="mailto:lukas.berent@tum.de"')
    expect(out).toContain('href="mailto:robert.wille@tum.de"')
    expect(out).toContain('title="Email lukas.berent@tum.de"')

    // 3. Codebase artifact repository link
    expect(out).toContain('href="https://github.com/cda-tum/mqt-core"')
    expect(out).toContain('Artifact Repository')
    expect(out).toContain('target="_blank"')

    // 4. Funding entities
    expect(out).toContain('Funding:')
    expect(out).toContain(
      'European Research Council (ERC); Bavarian State Ministry of Science and Arts; Federal Ministry of Education and Research (BMBF)',
    )

    // 5. Sovereignty & Risk flags (displayed in order: Schwarz Ecosystem, Competitor Involvement, Compliance Risks)
    expect(out).toContain('Compliance Risks:')
    expect(out).toContain('NO')
    expect(out).toContain('text-emerald-700')

    expect(out).toContain('Schwarz Ecosystem:')
    expect(out).toContain('YES (TUM)')
    expect(out).toContain('text-sky-700')

    expect(out).toContain('Competitor Involvement:')
    expect(out).toContain('None')
    expect(out).toContain('text-emerald-700')

    const ecoIdx = out.indexOf('Schwarz Ecosystem:')
    const compIdx = out.indexOf('Competitor Involvement:')
    const compRisksIdx = out.indexOf('Compliance Risks:')
    expect(ecoIdx).toBeLessThan(compIdx)
    expect(compIdx).toBeLessThan(compRisksIdx)
  })

  test('renders cleanly when only affiliations exist (no contacts, funding, links, flags)', () => {
    const onlyAffiliations: RiskAndAffiliation = {
      affiliations: ['University of Oxford'],
      author_contacts: [],
      funding_entities: [],
      flags: [],
      codebase_artifact_link: null,
    }
    const out = renderToStaticMarkup(<RiskAffiliationFlagging risk={onlyAffiliations} />)
    expect(out).toContain('University of Oxford')
    expect(out).not.toContain('Funding:')
    expect(out).not.toContain('href="mailto:')
    expect(out).not.toContain('Artifact Repository')
  })

  test('renders cleanly when only funding entities exist', () => {
    const onlyFunding: RiskAndAffiliation = {
      affiliations: [],
      author_contacts: [],
      funding_entities: ['BMBF Quantum Grant #42'],
      flags: [],
      codebase_artifact_link: null,
    }
    const out = renderToStaticMarkup(<RiskAffiliationFlagging risk={onlyFunding} />)
    expect(out).toContain('Funding:')
    expect(out).toContain('BMBF Quantum Grant #42')
    expect(out).not.toContain('BuildingLibraryIcon')
    expect(out).not.toContain('href="mailto:')
  })

  test('renders contact names as plain text without mailto when no @ is present', () => {
    const noEmailContact: RiskAndAffiliation = {
      affiliations: [],
      author_contacts: ['Dr. John Doe (Lead Author)', 'jane.doe@univ.edu'],
      funding_entities: [],
      flags: [],
      codebase_artifact_link: null,
    }
    const out = renderToStaticMarkup(<RiskAffiliationFlagging risk={noEmailContact} />)
    // Jane has @ -> mailto
    expect(out).toContain('href="mailto:jane.doe@univ.edu"')
    // John has no @ -> plain text, no mailto link
    expect(out).toContain('Dr. John Doe (Lead Author)')
    expect(out).not.toContain('href="mailto:Dr. John Doe')
  })

  test('handles null/empty flag dictionary values without throwing or crashing', () => {
    const brokenFlagRisk: RiskAndAffiliation = {
      affiliations: [],
      author_contacts: [],
      funding_entities: [],
      codebase_artifact_link: null,
      flags: [
        {
          key: 'gdpr',
          label: 'GDPR Sovereignty',
          value: '',
          status: 'safe',
          dict_value: { status: null, concerns: null },
        },
      ],
    }
    const out = renderToStaticMarkup(<RiskAffiliationFlagging risk={brokenFlagRisk} />)
    expect(out).toContain('Compliance Risks:')
    expect(out).toContain('text-emerald-700')
  })

  test('renders long author contacts list with responsive wrapping and line break classes', () => {
    const multiContactRisk: RiskAndAffiliation = {
      affiliations: ['University of California, Irvine'],
      author_contacts: [
        'haochx5@uci.edu',
        'bhardwb@uci.edu',
        'chouy10@uci.edu',
        'zhihenc5@uci.edu',
        'leyaoh5@uci.edu',
        'yifanz58@uci.edu',
        'yeq6@uci.edu',
        'saptarshi@uci.edu',
      ],
      funding_entities: [],
      codebase_artifact_link: null,
      flags: [],
    }
    const out = renderToStaticMarkup(<RiskAffiliationFlagging risk={multiContactRisk} />)

    // Verify wrapping and responsive containment classes
    expect(out).toContain('min-w-0')
    expect(out).toContain('max-w-full')
    expect(out).toContain('break-words')
    expect(out).toContain('[overflow-wrap:anywhere]')
    expect(out).toContain('break-all')

    // Verify all emails are rendered as mailto links
    expect(out).toContain('href="mailto:haochx5@uci.edu"')
    expect(out).toContain('href="mailto:saptarshi@uci.edu"')

    // Verify comma separation with space allowing browser line wrapping
    expect(out).toContain(', ')
  })
})

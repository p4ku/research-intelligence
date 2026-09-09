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

  test('unpacks stringified dictionary flags cleanly (Schwarz Ecosystem YES (TUM), Competitor None)', () => {
    const dictFlagsRisk: RiskAndAffiliation = {
      affiliations: [],
      author_contacts: [],
      funding_entities: [],
      flags: [
        {
          key: 'schwarz_ecosystem',
          label: 'Schwarz Ecosystem',
          value: "{'status': 'YES', 'matched_institutions': ['TUM']}",
          status: 'neutral',
        },
        {
          key: 'competitor',
          label: 'Competitor Involvement',
          value: "{'status': 'NO', 'matches': None}",
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
    expect(out).not.toContain("{'status'")
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

    // 5. Sovereignty & Risk flags
    expect(out).toContain('GDPR Sovereignty:')
    expect(out).toContain('NO')
    expect(out).toContain('text-emerald-700')

    expect(out).toContain('Schwarz Ecosystem:')
    expect(out).toContain('YES (TUM)')
    expect(out).toContain('text-sky-700')

    expect(out).toContain('Competitor Involvement:')
    expect(out).toContain('None')
    expect(out).toContain('text-emerald-700')
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
    expect(out).toContain('GDPR Sovereignty:')
    expect(out).toContain('text-emerald-700')
  })
})

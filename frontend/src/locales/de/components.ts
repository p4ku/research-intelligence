// Shared UI components: workshop signal strip, packet cards, top bar
export const dict: Record<string, string> = {
  // Dimension label used across score displays; an anglicism in German usage.
  TRL: 'TRL',
  // scanner-ui.tsx — trend stage pill (lowercase; CSS capitalizes) and TRL bands
  emerging: 'aufkommend',
  accelerating: 'beschleunigt',
  maturing: 'reifend',
  cooling: 'abkühlend',
  Research: 'Forschung',
  Development: 'Entwicklung',
  Deployment: 'Einsatz',
  // workshop-signals.tsx
  'Strategic relevance': 'Strategische Relevanz',
  'Schwarz fit': 'Schwarz-Eignung',
  // 'Readiness' lives in dashboard.ts ('Reifegrad') — one value, one module.
  'Author strength': 'Autoren-Stärke',
  'Beyond citation counts': 'Über Zitationszahlen hinaus',
  Reproducibility: 'Reproduzierbarkeit',
  'Code & artifacts': 'Code & Artefakte',
  'Code released': 'Code veröffentlicht',
  'No code released': 'Kein Code veröffentlicht',
  // packet-ui.tsx
  'Sent as {via}': 'Gesendet als {via}',
  '{n} paper': '{n} Paper',
  '{n} papers': '{n} Papers',
  'Sent {date}': 'Gesendet {date}',
  'Created {date}': 'Erstellt {date}',
  // top-bar.tsx
  'Page sections': 'Seitenabschnitte',
  // star.tsx + stars-client.tsx — the star is the MVP's only curation.
  // "markieren" (not "Stern"): the spec's German UI marks records, it does not award them.
  Star: 'Markieren',
  Starred: 'Markiert',
  'Star paper': 'Paper markieren',
  'Star briefing': 'Briefing markieren',
  'Star this paper': 'Dieses Paper markieren',
  'Unstar this paper': 'Markierung des Papers entfernen',
  'Star this briefing': 'Dieses Briefing markieren',
  'Unstar this briefing': 'Markierung des Briefings entfernen',
  'Nothing starred yet.': 'Noch nichts markiert.',
  'Could not save the star. Try again.':
    'Die Markierung konnte nicht gespeichert werden. Bitte erneut versuchen.',
}

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
}

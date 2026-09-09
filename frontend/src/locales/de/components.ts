// Shared UI components: workshop signal strip, packet cards, top bar
export const dict: Record<string, string> = {
  // Dimension label used across score displays; an anglicism in German usage.
  TRL: 'TRL',
  // scanner-ui.tsx — trend stage pill (lowercase; CSS capitalizes) and TRL bands
  emerging: 'aufkommend',
  accelerating: 'beschleunigend',
  maturing: 'reifend',
  cooling: 'abkühlend',
  Research: 'Forschung',
  Development: 'Entwicklung',
  Deployment: 'Einsatz',
  // workshop-signals.tsx
  'Strategic relevance': 'Strategische Relevanz',
  'Schwarz fit': 'Schwarz-Fit',
  // 'Readiness' lives in dashboard.ts ('Reifegrad') — one value, one module.
  'Author strength': 'Autorenstärke',
  'Beyond citation counts': 'Über Zitationszahlen hinaus',
  Reproducibility: 'Reproduzierbarkeit',
  'Code & artifacts': 'Code & Artefakte',
  'Code released': 'Code veröffentlicht',
  'No code released': 'Kein Code veröffentlicht',
  // page-nav.tsx — accessible name for the pager, not a visible label.
  Pagination: 'Seitennavigation',
  // packet-ui.tsx
  'Sent as {via}': 'Gesendet als {via}',
  '{n} paper': '{n} Paper',
  '{n} papers': '{n} Papers',
  'Sent {date}': 'Gesendet {date}',
  'Created {date}': 'Erstellt {date}',
  // corpus-search/ — the Home search field and its results panel
  'Search results': 'Suchergebnisse',
  Domains: 'Themenfelder',
  'Ask about “{title}”': 'Zu „{title}“ fragen',
  'See all {n} papers': 'Alle {n} Papers anzeigen',
  'Open paper': 'Paper öffnen',
  'Open Papers': 'Papers öffnen',
  'No paper with that id in your corpus.': 'Kein Paper mit dieser ID in Ihrem Bestand.',
  'No papers match “{q}”.': 'Keine Papers passen zu „{q}“.',
  'Search is unavailable — press Enter to open Papers.':
    'Die Suche ist nicht verfügbar – mit Enter Papers öffnen.',
  Try: 'Vorschläge',
  'Clear recent searches': 'Letzte Suchen löschen',
  '{n} matching': '{n} Treffer',
  'Opening Papers…': 'Papers werden geöffnet…',
  'Searching…': 'Suche läuft…',
  'Search papers': 'Papers durchsuchen',
  '{n} hits': '{n} Treffer',
  'Clear search': 'Suche zurücksetzen',
  'Search papers by topic, technology, title or author':
    'Papers nach Thema, Technologie, Titel oder Autor suchen',
  // star.tsx + stars-client.tsx — the star is the MVP's only curation.
  // "merken", not "markieren" (9 Sep 2026, relitigating the note that stood
  // here): a star is a private shortlist a reader comes back to, and
  // Merkliste / merken / gemerkt is the family every Schwarz shop and SAP
  // surface already uses for exactly that. "Markierung" reads as a flag
  // placed on a record for someone else to act on, which this is not.
  Star: 'Merken',
  // The ledgers' star column: a heading names a state, not an action, so the
  // column head reads "Gemerkt" while the button beside it still says "Merken".
  'column|Star': 'Gemerkt',
  Starred: 'Gemerkt',
  'Star paper': 'Paper merken',
  'Star briefing': 'Briefing merken',
  'Star this paper': 'Dieses Paper merken',
  'Unstar this paper': 'Paper aus der Merkliste entfernen',
  'Star this briefing': 'Dieses Briefing merken',
  'Unstar this briefing': 'Briefing aus der Merkliste entfernen',
  'Nothing starred yet.': 'Noch nichts auf der Merkliste.',
  'Could not save the star. Try again.':
    'Die Merkliste konnte nicht gespeichert werden. Bitte erneut versuchen.',
}

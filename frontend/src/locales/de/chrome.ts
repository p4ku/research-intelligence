// Shared chrome: sidebar, account menu, concept frame.
export const dict: Record<string, string> = {
  // Core sidebar nav labels. Scoped with the 'nav' gettext context so they
  // translate independently of the same English words used as page titles
  // elsewhere (e.g. the 'Papers'/'Tuning' page headings, which stay loanwords).
  'nav|Home': 'Start',
  'nav|Briefings': 'Briefings',
  'nav|Papers': 'Papers',
  'nav|Ask': 'Fragen',
  'nav|Runs': 'Runs',
  // Account-menu demo toggles (src/lib/features.ts). The labels reach t()
  // dynamically, so src/lib/features.test.ts guards them instead of i18n.test.ts.
  'Demo features': 'Demo-Funktionen',
  Stars: 'Markierungen',
  Settings: 'Einstellungen',
  'Hide core concepts': 'Kernkonzepte ausblenden',
  'Hide extra concepts': 'Zusatzkonzepte ausblenden',
  'Sign out': 'Abmelden',
  'Signing out…': 'Abmeldung läuft…',
  'Future Phase Concepts': 'Konzepte für zukünftige Phasen',
  'Phase 3a Concepts · Trends': 'Phase-3a-Konzepte · Trends',
  'Phase 3b Concepts · Author Intelligence': 'Phase-3b-Konzepte · Autoren-Intelligenz',
  Shared: 'Geteilt',
  Trends: 'Trends',
  'Tier 1 concepts': 'Tier-1-Konzepte',
  'Tier 2 concepts': 'Tier-2-Konzepte',
  Watchlist: 'Watchlist',
  'Designed for:': 'Konzipiert für:',
  // Route error boundaries (src/components/route-error.tsx + per-segment error.tsx).
  'Something went wrong loading this page.': 'Beim Laden dieser Seite ist ein Fehler aufgetreten.',
  Retry: 'Erneut versuchen',
  // Accessibility labels on the shell (mobile nav drawer, breadcrumb trail).
  'Open navigation': 'Navigation öffnen',
  'Close navigation': 'Navigation schließen',
  // Accessible name for the mobile nav drawer itself, not a visible label.
  Navigation: 'Navigation',
  Breadcrumb: 'Pfadnavigation',
  // Accessible name for the pager landmark (src/components/page-nav.tsx).
  Pagination: 'Seitennavigation',
  // Accessible name for icon-only dismiss buttons (the paper chat sheet today).
  Close: 'Schließen',
  'Retrying…': 'Wird erneut versucht …',
  'Reference {id}': 'Referenz {id}',
  "Couldn't load this page.": 'Diese Seite konnte nicht geladen werden.',
  "Couldn't load papers.": 'Die Papers konnten nicht geladen werden.',
  "Couldn't load this paper.": 'Dieses Paper konnte nicht geladen werden.',
  "Couldn't load Ask.": 'Fragen konnte nicht geladen werden.',
  "Couldn't load Settings.": 'Die Einstellungen konnten nicht geladen werden.',
  "Couldn't load Briefings.": 'Die Briefings konnten nicht geladen werden.',
  'Nothing was lost. Try again, or go back to Today.':
    'Es ist nichts verloren gegangen. Versuchen Sie es erneut oder kehren Sie zu Heute zurück.',
  'Nothing was lost. Try again in a moment.':
    'Es ist nichts verloren gegangen. Versuchen Sie es gleich erneut.',
  'Nothing you asked was lost. Try again in a moment.':
    'Ihre Fragen sind nicht verloren gegangen. Versuchen Sie es gleich erneut.',
  'No changes were saved. Try again in a moment.':
    'Es wurden keine Änderungen gespeichert. Versuchen Sie es gleich erneut.',
  'The paper is still there. Try again, or go back to the list.':
    'Das Paper ist weiterhin vorhanden. Versuchen Sie es erneut oder kehren Sie zur Liste zurück.',
  'Back to Today': 'Zurück zu Heute',
  'Back to Papers': 'Zurück zu Papers',
  'Back to Runs': 'Zurück zu Runs',
}

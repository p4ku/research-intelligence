// Shared chrome: sidebar, account menu, concept frame.
export const dict: Record<string, string> = {
  // Core sidebar nav labels. Scoped with the 'nav' gettext context so they
  // translate independently of the same English words used as page titles
  // elsewhere (e.g. the 'Papers'/'Tuning' page headings, which stay loanwords).
  'nav|Today': 'Heute',
  'nav|Briefings': 'Briefings',
  'nav|Papers': 'Papers',
  'nav|Tuning': 'Tuning',
  'nav|Ask': 'Fragen',
  'My account': 'Mein Konto',
  Settings: 'Einstellungen',
  'Privacy & access': 'Datenschutz & Zugriff',
  'Hide core concepts': 'Kernkonzepte ausblenden',
  'Hide extra concepts': 'Zusatzkonzepte ausblenden',
  'Sign out': 'Abmelden',
  'Future Phase Concepts': 'Konzepte für zukünftige Phasen',
  'Phase 3a Concepts · Trends': 'Phase-3a-Konzepte · Trends',
  'Phase 3b Concepts · Author Intelligence': 'Phase-3b-Konzepte · Autoren-Intelligenz',
  Shared: 'Geteilt',
  Trends: 'Trends',
  'Tier 1 concepts': 'Tier-1-Konzepte',
  'Tier 2 concepts': 'Tier-2-Konzepte',
  Watchlist: 'Watchlist',
  'Designed for:': 'Konzipiert für:',
  'No workspace': 'Kein Arbeitsbereich',
  'Switch workspace': 'Arbeitsbereich wechseln',
  // Route-group error boundary (src/app/(sidebar)/error.tsx). 'Retry' is shared
  // with papers/error.tsx, which had no translation before.
  'Something went wrong loading this page.': 'Beim Laden dieser Seite ist ein Fehler aufgetreten.',
  Retry: 'Erneut versuchen',
  // Accessibility labels on the shell (mobile nav drawer, breadcrumb trail).
  'Open navigation': 'Navigation öffnen',
  'Close navigation': 'Navigation schließen',
  Breadcrumb: 'Pfadnavigation',
}

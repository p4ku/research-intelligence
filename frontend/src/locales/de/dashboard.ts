// Core area: Dashboard (morning briefing, overnight numbers, top signals, the field)
export const dict: Record<string, string> = {
  Today: 'Heute',
  'Today · {date}': 'Heute · {date}',
  'Open briefing →': 'Briefing öffnen →',
  'Assembled automatically from this run.': 'Automatisch aus diesem Lauf zusammengestellt.',
  'No completed runs yet.': 'Noch keine abgeschlossenen Läufe.',
  'Run of {date}: {fetched} papers fetched, {passed} passed screening, {n} listed below.':
    'Lauf vom {date}: {fetched} Papers geladen, {passed} durch das Screening, {n} unten gelistet.',
  'Once a pipeline run completes, its papers appear here.':
    'Sobald ein Pipeline-Lauf abgeschlossen ist, erscheinen seine Papers hier.',
  'Good morning, {name}': 'Guten Morgen, {name}',
  // Fallback when the session carries no name; interpolated into the greeting above.
  there: 'zusammen',
  "Here's what the scanner surfaced overnight across your focus fields.":
    'Das hat der Scanner über Nacht in Ihren Fokusfeldern zutage gefördert.',
  Identified: 'Identifiziert',
  Evaluated: 'Bewertet',
  'Deep-dived': 'Vertieft',
  'vs. yesterday': 'ggü. gestern',
  'Morning briefing': 'Morgen-Briefing',
  'Read the briefing →': 'Briefing lesen →',
  'Top signals today': 'Top-Signale heute',
  'All papers →': 'Alle Papers →',
  'Novelty {novelty} · Significance {significance}':
    'Neuheit {novelty} · Signifikanz {significance}',
  'The field': 'Das Feld',
  'Open radar →': 'Radar öffnen →',
  'Engage early': 'Früh einsteigen',
  'Act now': 'Jetzt handeln',
  Archive: 'Archivieren',
  Monitor: 'Beobachten',
  'Fastest rising': 'Am stärksten steigend',
  Summary: 'Zusammenfassung',
  'Lead story': 'Aufmacher',
  '{identified} identified → {evaluated} screened → {deepDived} deep dives':
    '{identified} identifiziert → {evaluated} gesichtet → {deepDived} Tiefenanalysen',
  'Strategic relevance': 'Strategische Relevanz',
  // Redesigned dashboard: the morning brief as the daily entry point.
  Headlines: 'Schlagzeilen',
  'The papers': 'Die Papers',
  'Full analysis →': 'Vollständige Analyse →',
  'this run': 'dieser Lauf',
  'to teams': 'an Teams',
  'Headline stories': 'Schlagzeilen',
  '1 lead · {n} more': '1 Aufmacher · {n} weitere',
  'Browse the full corpus →': 'Gesamten Korpus durchsuchen →',
  'Every paper this run scored above the signal threshold — the shortlist behind the headlines. Filter by field or readiness to find where to drill in.':
    'Jedes Paper, das dieser Lauf über die Signalschwelle bewertet hat — die Auswahl hinter den Schlagzeilen. Filtern Sie nach Feld oder Reifegrad, um zu entscheiden, wo Sie tiefer einsteigen.',
  'The run': 'Der Lauf',
  'Focus fields': 'Fokusfelder',
  // Compact funnel strip under the greeting.
  identified: 'identifiziert',
  screened: 'gesichtet',
  'deep-dived': 'vertieft',
  'handed off': 'übergeben',
  Signal: 'Signal',
  Newest: 'Neueste',
  Readiness: 'Reifegrad',
  'No papers in this run match those filters.':
    'Keine Papers in diesem Lauf entsprechen diesen Filtern.',
  'No papers in this run.': 'Keine Papers in diesem Lauf.',
  'Every paper this run scored above the signal threshold — the shortlist behind the headlines.':
    'Jedes Paper, das dieser Lauf über die Signalschwelle bewertet hat — die Auswahl hinter den Schlagzeilen.',
  Sort: 'Sortieren',
  Previous: 'Zurück',
  Next: 'Weiter',
  'Overall score': 'Gesamtscore',
  'Schwarz Fit': 'Schwarz-Eignung',
  'Showing the {n} papers this run surfaced above threshold.':
    'Zeigt die {n} Papers, die dieser Lauf über der Schwelle zutage gefördert hat.',
  // Pagination for the run's papers.
  Pages: 'Seiten',
  'Showing {from}–{to} of {total}': 'Zeige {from}–{to} von {total}',
  '{current} / {total}': '{current} / {total}',
  '← Prev': '← Zurück',
  'Next →': 'Weiter →',
  // Flat daily digest (no lead story): funnel at daily volumes + today in brief.
  'Today in brief': 'Heute in Kürze',
  Screened: 'Gesichtet',
  'matched the focus fields': 'den Fokusfeldern zugeordnet',
  Included: 'Aufgenommen',
  'cleared the signal bar': 'über der Signalschwelle',
  'In the briefing': 'Im Briefing',
  'listed below': 'unten gelistet',
  // Streaming skeleton statuses (Skeleton.Region announcements).
  'Loading the funnel': 'Die Kennzahlen werden geladen',
  'Loading today’s brief': '„Heute in Kürze“ wird geladen',
  'Loading the papers': 'Die Papers werden geladen',
  Papers: 'Papers',
  'Not yet active': 'Noch nicht aktiv',
  // Home (7 Sep 2026): search, the masthead, Recent Briefings, Start New Briefing.
  Home: 'Start',
  'Search papers by topic, technology, title or author':
    'Papers nach Thema, Technologie, Titel oder Autor suchen',
  'Recent briefings': 'Aktuelle Briefings',
  'View all briefings →': 'Alle Briefings anzeigen →',
  'Ask about a paper →': 'Zu einem Paper fragen →',
  'No briefings have been generated yet.': 'Es wurden noch keine Briefings erstellt.',
  'Loading the briefing': 'Das Briefing wird geladen',
  'Loading recent briefings': 'Aktuelle Briefings werden geladen',
  'generated {date}': 'erstellt {date}',
  '{screened} screened → {included} included → {lead} lead the briefing':
    '{screened} gesichtet → {included} aufgenommen → {lead} führen das Briefing an',
  '{screened} screened → {included} included': '{screened} gesichtet → {included} aufgenommen',
  'Top of the briefing': 'Spitze des Briefings',
  'The brief for this run is not available.': 'Das Briefing zu diesem Lauf ist nicht verfügbar.',
  'No papers met the inclusion criteria for this briefing.':
    'Kein Paper hat die Aufnahmekriterien für dieses Briefing erfüllt.',
  Period: 'Zeitraum',
  Generated: 'Erstellt',
  Current: 'Aktuell',
  Processing: 'In Arbeit',
  Failed: 'Fehlgeschlagen',
  'started {time} UTC': 'gestartet {time} UTC',
  'failed {date}': 'fehlgeschlagen {date}',
  'From {date}': 'Ab {date}',
  'Until {date}': 'Bis {date}',
  'Last {n} days': 'Letzte {n} Tage',
  'Start new briefing': 'Neues Briefing starten',
  From: 'Von',
  To: 'Bis',
  'Run pipeline': 'Pipeline starten',
  'Starting…': 'Wird gestartet…',
  'One run at a time across all analysts. When it finishes, the new briefing leads the page.':
    'Ein Lauf zur Zeit, über alle Analysten hinweg. Sobald er fertig ist, führt das neue Briefing die Seite an.',
  '{domain} is running. Briefings and papers stay available meanwhile.':
    '{domain} läuft. Briefings und Papers bleiben währenddessen verfügbar.',
  "Couldn't start the run. Try again.":
    'Der Lauf konnte nicht gestartet werden. Bitte erneut versuchen.',
  'A dense day for Hybrid Computing: agents pick up deterministic control flow, recovery-first tool use, and a learned memory at a sixth of the tokens; durable content credentials survive real platform pipelines, and verifiable delegation answers the know-your-agent question at checkout.':
    'Ein dichter Tag für Hybrid Computing: Agenten erhalten deterministischen Kontrollfluss, Recovery-First-Tool-Use und ein gelerntes Gedächtnis bei einem Sechstel der Tokens; dauerhafte Content Credentials überstehen echte Plattform-Pipelines, und verifizierbare Delegation beantwortet die Know-your-Agent-Frage an der Kasse.',
}

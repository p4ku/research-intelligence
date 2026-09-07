// Core area: Papers list, filters, and paper detail page
export const dict: Record<string, string> = {
  // Papers list page
  Corpus: 'Korpus',
  Papers: 'Papers',

  // Result count and filter context
  paper: 'Paper',
  papers: 'Papers',
  'last {n} days': 'letzte {n} Tage',
  'full corpus': 'gesamter Korpus',
  'matching “{q}”': 'passend zu „{q}“',
  'Reset filters': 'Filter zurücksetzen',
  'No papers match these filters.': 'Keine Papers entsprechen diesen Filtern.',

  // Filter sidebar
  Search: 'Suche',
  'Search papers': 'Papers durchsuchen',
  '{n} hits': '{n} Treffer',
  'Clear search': 'Suche zurücksetzen',
  'Sort by': 'Sortieren nach',
  'TRL window': 'TRL-Fenster',
  'Minimum TRL': 'Minimales TRL',
  'Maximum TRL': 'Maximales TRL',
  to: 'bis',
  '1–3 research': '1–3 Forschung',
  '4–6 development': '4–6 Entwicklung',
  '7–9 deployment': '7–9 Einsatz',

  // Sort options
  'Signal score': 'Signal-Score',
  'Most recent': 'Neueste zuerst',
  'Search titles, abstracts, authors, arXiv ids…':
    'Titel, Abstracts, Autoren, arXiv-IDs durchsuchen…',

  // Screening filter and pills
  Screening: 'Screening',
  Passed: 'Bestanden',
  'Abstract passed': 'Abstract bestanden',
  'Full text passed': 'Volltext bestanden',
  Accepted: 'Akzeptiert',
  Borderline: 'Grenzfall',
  Pending: 'Ausstehend',
  Rejected: 'Abgelehnt',
  Withdrawn: 'Zurückgezogen',
  'All statuses': 'Alle Status',
  'through screening': 'durch das Screening',
  Ingested: 'Aufgenommen',
  Unscored: 'Nicht bewertet',

  // Domain scope and empty states
  'All domains': 'Alle Domänen',
  Domain: 'Domäne',
  'No papers yet.': 'Noch keine Papers.',
  'Something went wrong loading papers.': 'Beim Laden der Papers ist ein Fehler aufgetreten.',
  Retry: 'Erneut versuchen',

  // Published windows
  'Last 24 hours': 'Letzte 24 Stunden',
  'Last 7 days': 'Letzte 7 Tage',
  'Last 30 days': 'Letzte 30 Tage',
  'This quarter': 'Dieses Quartal',
  'All time': 'Gesamter Zeitraum',

  // Signal-strength filter
  'Signal strength': 'Signalstärke',
  'Minimum score': 'Mindest-Score',
  Any: 'Beliebig',
  'Any signal': 'Jedes Signal',
  'Only the strongest': 'Nur die stärksten',
  'Signal ≥ {n}': 'Signal ≥ {n}',

  // Paper detail
  'All papers': 'Alle Papers',
  'Signal Score': 'Signal-Score',
  Profile: 'Profil',
  Dimensions: 'Dimensionen',
  'Scored by the domain’s extraction definitions, with the model’s rationale where it gave one.':
    'Bewertet nach den Extraktionsdefinitionen der Domäne, mit Begründung des Modells, wo vorhanden.',
  Formula: 'Formel',
  Variables: 'Variablen',
  'Formula error': 'Formelfehler',
  'Formula inputs': 'Formeleingaben',
  'Other values': 'Weitere Werte',
  '{n} extracted fields': '{n} extrahierte Felder',
  '{n} more recorded values': '{n} weitere erfasste Werte',
  Yes: 'Ja',
  No: 'Nein',
  // Signal ledger
  'What the score is made of — and what would move it.':
    'Woraus sich der Score zusammensetzt — und was ihn verändern würde.',
  'Fit score': 'Fit-Score',
  'Novelty score': 'Neuheits-Score',
  'TRL level': 'TRL-Stufe',
  'as scored': 'wie bewertet',
  'Reset to actual {n}': 'Zurück auf tatsächlich {n}',
  'TRL {n}+ bonus': 'Bonus ab TRL {n}',
  'Below TRL {n} the score is 0, whatever the fit and novelty.':
    'Unter TRL {n} ist der Score 0, unabhängig von Fit und Neuheit.',
  gate: 'Schwelle',
  actual: 'tatsächlich',
  'Not scored yet': 'Noch nicht bewertet',
  'Composite score from the domain’s signal-score formula.':
    'Gesamtscore aus der Signal-Score-Formel der Domäne.',
  Evidence: 'Belege',
  Confidence: 'Konfidenz',
  'Needs review': 'Prüfung nötig',
  'No screening notes.': 'Keine Screening-Notizen.',
  Files: 'Dateien',
  'Open on arXiv': 'Auf arXiv öffnen',
  'Open DOI': 'DOI öffnen',
  'Stored PDF': 'Gespeichertes PDF',
  'Stored markdown': 'Gespeichertes Markdown',
  'Stored in the research archive — download is not yet available.':
    'Im Forschungsarchiv gespeichert — der Download ist noch nicht verfügbar.',
  'No files recorded.': 'Keine Dateien hinterlegt.',
  'et al.': 'et al.',
  'Why did it score {score}?': 'Warum wurde es mit {score} bewertet?',
  'What does this paper enable?': 'Was ermöglicht dieses Paper?',
  'How solid is the evidence?': 'Wie belastbar sind die Belege?',
  Abstract: 'Abstract',

  // Paper analysis (sidecar layout)
  'Schwarz Score': 'Schwarz-Score',
  Assessment: 'Bewertung',
  'View original paper': 'Originalpaper ansehen',
  'Previous paper': 'Vorheriges Paper',
  'Next paper': 'Nächstes Paper',
  '{n} of {total}': '{n} von {total}',
  'No rationale recorded.': 'Keine Begründung hinterlegt.',
  'Confidence {n}': 'Konfidenz {n}',
  Source: 'Quelle',
  Run: 'Lauf',
  'Generating…': 'Wird generiert…',
  'Ask a question about this paper…': 'Eine Frage zu diesem Paper stellen…',

  // Ask-this-paper rail
  'Ask this paper': 'Paper befragen',
  'Reading the full text…': 'Der Volltext wird gelesen…',
  'Ask about {title}': 'Zu {title} fragen',
  'Questions here are answered from this paper alone.':
    'Fragen hier werden allein aus diesem Paper beantwortet.',
  'Ask a question about this paper': 'Eine Frage zu diesem Paper stellen',
  "Couldn't load this paper's earlier questions.":
    'Die früheren Fragen zu diesem Paper konnten nicht geladen werden.',
  'A new thread will start if you ask now.': 'Wenn Sie jetzt fragen, beginnt ein neues Gespräch.',
  'Ask about this paper…': 'Zu diesem Paper fragen…',
  Send: 'Senden',
  'Loading the paper': 'Das Paper wird geladen',
  "I couldn't ground an answer to that in this paper's text — try asking about what it enables, how solid the evidence is, or where it could apply.":
    'Dazu ließ sich im Text dieses Papers keine belegte Antwort finden — fragen Sie etwa, was es ermöglicht, wie belastbar die Evidenz ist oder wo es einsetzbar wäre.',
}

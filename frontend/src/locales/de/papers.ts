// Core area: Papers list, filters, and paper detail page
export const dict: Record<string, string> = {
  // Papers list page
  Corpus: 'Bestand',
  Papers: 'Papers',

  // Result count and filter context
  paper: 'Paper',
  papers: 'Papers',
  'last {n} days': 'letzte {n} Tage',
  'full corpus': 'gesamter Bestand',
  'Showing the newest {n} of {m} papers': 'Die neuesten {n} von {m} Papers',
  'Could not load these papers.': 'Diese Papers konnten nicht geladen werden.',
  'matching “{q}”': 'passend zu „{q}“',
  'Reset filters': 'Filter zurücksetzen',
  'No papers match these filters.': 'Keine Papers passen zu diesen Filtern.',

  // Filter sidebar
  Search: 'Suche',
  'Search papers': 'Papers durchsuchen',
  '{n} hits': '{n} Treffer',
  'Clear search': 'Suche zurücksetzen',
  'Sort by': 'Sortierung',
  'TRL window': 'TRL-Fenster',
  'Minimum TRL': 'TRL min.',
  'Maximum TRL': 'TRL max.',
  to: 'bis',
  '1–3 research': '1–3 Forschung',
  '4–6 development': '4–6 Entwicklung',
  '7–9 deployment': '7–9 Einsatz',

  // Sort options
  'Signal score': 'Signal-Score',
  Relevance: 'Relevanz',
  'Most recent': 'Neueste zuerst',
  '{n} more matches in other screening states — show them':
    '{n} weitere Treffer in anderen Screening-Stufen – anzeigen',
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
  'All statuses': 'Alle Stufen',
  'through screening': 'Screening bestanden',
  Ingested: 'Erfasst',
  Unscored: 'Nicht bewertet',

  // Domain scope and empty states
  'All domains': 'Alle Themenfelder',
  Domain: 'Themenfeld',
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
  'Any signal': 'Jedes Signal',
  'Only the strongest': 'Nur die stärksten',
  'Signal ≥ {n}': 'Signal ≥ {n}',

  // Paper detail
  'All papers': 'Alle Papers',
  'Signal Score': 'Signal-Score',
  Profile: 'Profil',
  Dimensions: 'Dimensionen',
  'Scored by the domain’s extraction definitions, with the model’s rationale where it gave one.':
    'Bewertet nach den Extraktionsdefinitionen des Themenfelds, mit Begründung des Modells, wo vorhanden.',
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
    'Woraus sich der Score zusammensetzt – und was ihn verändern würde.',
  'Fit score': 'Fit-Score',
  'Novelty score': 'Neuheits-Score',
  'TRL level': 'TRL-Stufe',
  'as scored': 'wie bewertet',
  'Reset to actual {n}': 'Zurück auf den Istwert {n}',
  'TRL {n}+ bonus': 'Bonus ab TRL {n}',
  'Below TRL {n} the score is 0, whatever the fit and novelty.':
    'Unter TRL {n} ist der Score 0, unabhängig von Fit und Neuheit.',
  gate: 'Schwelle',
  actual: 'Istwert',
  'Not scored yet': 'Noch nicht bewertet',
  'Composite score from the domain’s signal-score formula.':
    'Gesamt-Score aus der Signal-Score-Formel des Themenfelds.',
  Evidence: 'Belege',
  Confidence: 'Konfidenz',
  'Needs review': 'Prüfung erforderlich',
  'No screening notes.': 'Keine Screening-Notizen.',
  Files: 'Dateien',
  'Open on arXiv': 'Auf arXiv öffnen',
  'Open DOI': 'DOI öffnen',
  'Stored PDF': 'Gespeichertes PDF',
  'Stored markdown': 'Gespeichertes Markdown',
  'No files recorded.': 'Keine Dateien hinterlegt.',
  'et al.': 'et al.',
  'Why did it score {score}?': 'Warum wurde es mit {score} bewertet?',
  'What does this paper enable?': 'Was ermöglicht dieses Paper?',
  'How solid is the evidence?': 'Wie belastbar sind die Belege?',
  Abstract: 'Abstract',

  // Paper analysis (sidecar layout)
  'Total Score': 'Gesamt-Score',
  'Schwarz Score': 'Schwarz-Score',
  'View original paper': 'Originalpaper ansehen',
  'Previous paper': 'Vorheriges Paper',
  'Next paper': 'Nächstes Paper',
  'Back to briefing': 'Zurück zum Briefing',
  '{n} of {total}': '{n} von {total}',
  'No rationale recorded.': 'Keine Begründung hinterlegt.',
  'Confidence {n}': 'Konfidenz {n}',
  Source: 'Quelle',
  Run: 'Lauf',
  'Ask a question about this paper…': 'Eine Frage zu diesem Paper stellen…',

  // Provenance and masthead dates: the date is inside the phrase, so the
  // components interpolate rather than concatenate ("Erfasst am 3. Juli 2026").
  'Ingested {date}': 'Erfasst am {date}',
  'Published {date}': 'Veröffentlicht am {date}',

  /*
   * Display names for the dimensions the product itself scores, under the
   * 'dimension' context (lib/papers/dimension-label.ts). Every other
   * definition name is the domain's own and stays as the backend wrote it.
   * "Signifikanz" is a false friend for Significance — the reading here is
   * "how much it matters", which is Bedeutung.
   */
  'dimension|Rigour': 'Methodik',
  'dimension|Novelty': 'Neuheit',
  'dimension|Significance': 'Bedeutung',
  'dimension|Readiness': 'Reifegrad',
  'dimension|Schwarz Fit': 'Schwarz-Fit',
  'dimension|Research Quality': 'Forschungsqualität',
  // Two names the frontend supplies itself, so they are ours to translate.
  'Technology being Assessed': 'Bewertete Technologie',
  Extraction: 'Extraktion',
  'Sub-score: {n}': 'Teilscore: {n}',

  // Risk & affiliation card (affiliation-flags.tsx). The verdicts are the
  // frontend's own wording, not backend prose.
  'Artifact Repository': 'Artefakt-Repository',
  'View codebase or artifact': 'Code oder Artefakt ansehen',
  'Email {contact}': 'E-Mail an {contact}',
  'Funding: ': 'Förderung: ',
  'Risk Score:': 'Risiko-Score:',
  'Compliance Risks': 'Compliance-Risiken',
  YES: 'JA',
  NO: 'NEIN',
  None: 'Keine',

  // Paper analysis (definition-shaped assessment)
  Published: 'Veröffentlicht',
  'Abstract stage': 'Abstract-Stufe',
  'Full text': 'Volltext',
  'Benchmark Control': 'Benchmark-Kontrolle',
  'Scoring formula': 'Bewertungsformel',
  'Rule verified': 'Regelbasiert geprüft',
  'Human verified': 'Von Menschen geprüft',

  // Ask-this-paper rail
  'Ask this paper': 'Paper befragen',
  'Reading the full text…': 'Der Volltext wird gelesen…',
  'Ask about {title}': 'Zu {title} fragen',
  'Questions here are answered from this paper alone.':
    'Fragen hier werden allein aus diesem Paper beantwortet.',
  'Ask a question about this paper': 'Eine Frage zu diesem Paper stellen',
  // The chat sheet's dismiss button.
  Close: 'Schließen',
  'Ask about this paper…': 'Zu diesem Paper fragen…',
  'Answered from this paper alone.': 'Wird allein aus diesem Paper beantwortet.',
  // A paper whose PDF was never stored (URL only): the chat has the abstract, nothing more.
  "Answered from this paper's abstract only.":
    'Wird allein aus dem Abstract dieses Papers beantwortet.',
  'Reading the abstract…': 'Der Abstract wird gelesen…',
  'What would you like to know?': 'Was möchten Sie wissen?',
  // The console (Column layout, 9 Sep 2026): the thread outlives the surface.
  'Ask a follow-up…': 'Eine Rückfrage stellen…',
  'Continue "{title}"': '„{title}“ fortsetzen',
  'Answering…': 'Antwort läuft…',
  Collapse: 'Einklappen',
  Recent: 'Zuletzt',
  '1 chat': '1 Chat',
  '{count} chats': '{count} Chats',
  'Questions about this paper are filed here.': 'Fragen zu diesem Paper werden hier abgelegt.',
  Send: 'Senden',
  'Loading the paper': 'Das Paper wird geladen',
  "I couldn't ground an answer to that in this paper's text — try asking about what it enables, how solid the evidence is, or where it could apply.":
    'Dazu ließ sich im Text dieses Papers keine belegte Antwort finden – fragen Sie etwa, was es ermöglicht, wie belastbar die Belege sind oder wo es einsetzbar wäre.',

  // Paper comments
  Comments: 'Kommentare',
  'Paper comments': 'Paper-Kommentare',
  'Could not load comments.': 'Kommentare konnten nicht geladen werden.',
  'Comment added': 'Kommentar hinzugefügt',
  'Could not post comment. Please try again.':
    'Kommentar konnte nicht gesendet werden. Bitte versuchen Sie es erneut.',
  'Comment deleted': 'Kommentar gelöscht',
  'Could not delete comment.': 'Kommentar konnte nicht gelöscht werden.',
  'No comments yet. Start a discussion.': 'Noch keine Kommentare. Starten Sie eine Diskussion.',
  '1 note on this paper.': '1 Notiz zu diesem Paper.',
  'notes on this paper.': 'Notizen zu diesem Paper.',
  'Add a comment…': 'Kommentar hinzufügen…',
  'No comments yet.': 'Noch keine Kommentare.',
  'Leave the first note or discussion point below.':
    'Hinterlassen Sie unten die erste Notiz oder Diskussionspunkt.',
  Anonymous: 'Anonym',
  You: 'Sie',
  edited: 'bearbeitet',
  'Delete comment': 'Kommentar löschen',
  'Edit comment': 'Kommentar bearbeiten',
  'Comment updated': 'Kommentar aktualisiert',
  'Could not update comment.': 'Kommentar konnte nicht aktualisiert werden.',
  'to cancel': 'zum Abbrechen',
  'to save': 'zum Speichern',
  'Saving…': 'Wird gespeichert…',
  Save: 'Speichern',
  Cancel: 'Abbrechen',
  'Write a comment… (Markdown supported)': 'Kommentar verfassen… (Markdown unterstützt)',
  'to send': 'zum Senden',
  'Posting…': 'Wird gesendet…',
  Comment: 'Kommentieren',
  'Delete comment?': 'Kommentar löschen?',
  'This comment will be permanently removed. This action cannot be undone.':
    'Dieser Kommentar wird dauerhaft entfernt. Diese Aktion kann nicht rückgängig gemacht werden.',
  'Show score breakdown': 'Aufschlüsselung anzeigen',
  'Hide score breakdown': 'Aufschlüsselung ausblenden',
  'Add reaction': 'Reaktion hinzufügen',
  'Could not update reaction.': 'Reaktion konnte nicht aktualisiert werden.',
  'Agree / Useful': 'Zustimmen / Nützlich',
  Disagree: 'Nicht einverstanden',
  Insightful: 'Aufschlussreich',
  'Priority / Breakthrough': 'Priorität / Durchbruch',
  'Clarification Needed': 'Klärung erforderlich',
  Appreciated: 'Geschätzt',
}

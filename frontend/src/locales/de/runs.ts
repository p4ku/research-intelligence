// Runs: the pipeline-run list and the run detail page (src/app/(sidebar)/runs).
//
// Keys reused from other area modules and deliberately NOT repeated here, so
// the audit cannot see two values for one key: All (briefing), Domain, Passed,
// Pending, Run, papers, Search, Screening, Extraction, Signal score (papers),
// Failed, Summary, screened (dashboard), passed, Stop, Cancel (ask).
export const dict: Record<string, string> = {
  // Page shell
  Runs: 'Läufe',
  Pipeline: 'Pipeline',
  'Every pipeline run across your domains — what it produced, what it cost, and how long it took.':
    'Jeder Pipeline-Lauf in Ihren Themenfeldern – was er erzeugt hat, was er gekostet hat und wie lange er gedauert hat.',
  'Loading the runs': 'Die Läufe werden geladen',

  // Stat band
  'Papers fetched': 'Abgerufene Papers',
  'Passed screening': 'Screening bestanden',
  'Total spend': 'Gesamtkosten',
  '{share} of {n} fetched': '{share} von {n} abgerufenen Papers',

  // Filter strip (tab labels: All / Failed come from the shared keys)
  'Filter runs by outcome': 'Läufe nach Ergebnis filtern',

  // Run and step status words
  Completed: 'Abgeschlossen',
  Running: 'Läuft',
  Aborted: 'Abgebrochen',
  Skipped: 'Übersprungen',

  // Runs table
  'Run {id}': 'Lauf {id}',
  'Started (UTC)': 'Gestartet (UTC)',
  Outcome: 'Ergebnis',
  'Last stage': 'Letzte Stufe',
  Fetched: 'Abgerufen',
  Duration: 'Dauer',
  Cost: 'Kosten',

  // Stop a run (the button and the action reuse Stop; Cancel is shared too)
  'Stop this run?': 'Diesen Lauf stoppen?',
  'The {domain} run will stop once its current step finishes. This cannot be undone.':
    'Der Lauf für {domain} wird nach dem aktuellen Schritt gestoppt. Dies kann nicht rückgängig gemacht werden.',
  'Stopping…': 'Wird gestoppt…',
  'This run has already ended.': 'Dieser Lauf ist bereits beendet.',
  'Only an admin or manager of this domain can stop its runs.':
    'Nur Admins oder Manager dieses Themenfelds können seine Läufe stoppen.',
  "Couldn't stop this run. Try again.":
    'Der Lauf konnte nicht gestoppt werden. Versuchen Sie es erneut.',

  // Rerun a run
  Rerun: 'Erneut ausführen',
  'Rerun this pipeline?': 'Diese Pipeline erneut ausführen?',
  'The {domain} pipeline run will re-execute from the failed step or beginning.':
    'Der Pipeline-Lauf für {domain} wird ab dem fehlgeschlagenen Schritt oder von Beginn an erneut ausgeführt.',
  'Rerunning…': 'Wird erneut ausgeführt…',
  'Only an admin of this domain can rerun its runs.':
    'Nur ein Admin dieses Themenfelds kann seine Läufe erneut ausführen.',
  "Couldn't rerun this run. Try again.":
    'Der Lauf konnte nicht erneut ausgeführt werden. Versuchen Sie es erneut.',

  // Empty states
  'No pipeline runs yet.': 'Noch keine Pipeline-Läufe.',
  'No runs match this filter. {n} run in total.':
    'Kein Lauf passt zu diesem Filter. {n} Lauf insgesamt.',
  'No runs match this filter. {n} runs in total.':
    'Kein Lauf passt zu diesem Filter. {n} Läufe insgesamt.',

  // Pipeline stages. Reached through `t(stageLabel(stage))` — the English
  // labels in src/lib/bff/pipeline-runs/schema.ts are the keys, so the audit
  // reports these as having no static caller.
  OCR: 'OCR',
  'Full-text screening': 'Volltext-Screening',
  'Abstract screening': 'Abstract-Screening',
  'Deep research': 'Tiefenrecherche',

  // Step titles. Frontend copy, not backend content: the English strings live
  // in src/lib/bff/component-runs/normalise.ts and reach t() dynamically as
  // `t(step.label)`, so run-presentation.test.ts guards this list instead of
  // the static audit. Search, Screening, Extraction, Signal score and Deep
  // research are already keys above or in papers.ts and are not repeated.
  Download: 'Download',
  Metrics: 'Kennzahlen',
  Reporting: 'Berichterstellung',
  'Unrecognised step': 'Unbekannter Schritt',
  'arXiv search': 'arXiv-Suche',
  'OpenAlex search': 'OpenAlex-Suche',
  'Lens search': 'Lens-Suche',
  'PubMed search': 'PubMed-Suche',
  'Layout OCR': 'Layout-OCR',
  'Parameter extraction': 'Parameterextraktion',
  'Executive narrative': 'Management-Zusammenfassung',

  // Run detail: funnel band
  'from the sources': 'aus den Quellen',
  '{share} of fetched': '{share} der abgerufenen Papers',
  'Papers stored': 'Gespeicherte Papers',
  'rows in this run': 'Zeilen in diesem Lauf',
  Extractions: 'Extraktionen',
  'parameter values': 'Parameterwerte',
  'Loading the run': 'Der Lauf wird geladen',

  // Run detail: facts
  Tokens: 'Token',
  '{in} in · {out} out': '{in} ein · {out} aus',
  'Triggered by': 'Ausgelöst von',
  System: 'System',
  Mode: 'Modus',
  'Reprocess existing': 'Vorhandene neu verarbeiten',
  'Skip duplicates': 'Duplikate überspringen',
  'Last stage dispatched': 'Zuletzt gestartete Stufe',
  Duplicates: 'Duplikate',
  '{n} file': '{n} Datei',
  '{n} files': '{n} Dateien',
  Artefacts: 'Artefakte',

  // Run detail: step timeline
  Steps: 'Schritte',
  'Loading the steps': 'Die Schritte werden geladen',
  '{n} step': '{n} Schritt',
  '{n} steps': '{n} Schritte',
  '{usd} attributed': '{usd} zugeordnet',
  '{usd} unattributed': '{usd} nicht zugeordnet',
  '{n} step did not succeed: {steps}.': '{n} Schritt war nicht erfolgreich: {steps}.',
  '{n} steps did not succeed: {steps}.': '{n} Schritte waren nicht erfolgreich: {steps}.',
  'No steps recorded for this run.': 'Für diesen Lauf wurden keine Schritte erfasst.',
  'Attempt {n}': 'Versuch {n}',
  'This step ran more than once in this pipeline run':
    'Dieser Schritt wurde in diesem Pipeline-Lauf mehrfach ausgeführt',
  '{n} tok': '{n} Token',

  // Step summaries: the count labels read as "12 abgerufen", so they stay
  // lowercase participles where German allows it.
  new: 'neu',
  fetched: 'abgerufen',
  duplicates: 'Duplikate',
  downloaded: 'heruntergeladen',
  cached: 'aus dem Cache',
  failed: 'fehlgeschlagen',
  converted: 'konvertiert',
  rejected: 'abgelehnt',
  withdrawn: 'zurückgezogen',
  extractions: 'Extraktionen',
  definitions: 'Definitionen',
  characters: 'Zeichen',
  'of {total} scored': 'von {total} bewertet',
  avg: 'Ø',
  max: 'max.',
  'Report generated': 'Bericht erstellt',
  'No report': 'Kein Bericht',
  'No metrics recorded': 'Keine Metriken erfasst',
}

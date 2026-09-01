// Scoring — the read-only formula/weights page. The code snippet, variable
// keys, and paper titles are backend content and stay untranslated.
export const dict: Record<string, string> = {
  Scoring: 'Scoring',
  Method: 'Methodik',
  'How this workspace ranks papers. The formula lives in the backend and is applied to every paper as it is scored.':
    'Wie dieser Workspace Papers bewertet. Die Formel liegt im Backend und wird auf jedes Paper beim Scoring angewendet.',
  'The formula': 'Die Formel',
  'How papers are scored': 'So werden Papers bewertet',
  'Fit counts for 60% of the score and novelty for 40%.':
    'Fit macht 60 % des Scores aus, Neuheit 40 %.',
  'Papers below TRL {n} score 0.': 'Papers unter TRL {n} erhalten 0.',
  'TRL {n} and above earns a ×1.25 bonus.': 'Ab TRL {n} gibt es einen Bonus von ×1,25.',
  'This workspace uses a custom formula maintained in the backend.':
    'Dieser Workspace nutzt eine eigene Formel, die im Backend gepflegt wird.',
  'Read from the most recent scoring run.': 'Aus dem letzten Scoring-Lauf gelesen.',
  'Read from the workspace.': 'Aus dem Workspace gelesen.',
  'Fixture formula (stub source).': 'Fixture-Formel (Stub-Quelle).',
  'No paper has been scored yet, so the formula has not surfaced.':
    'Noch wurde kein Paper bewertet, daher ist die Formel noch nicht sichtbar.',
  Variables: 'Variablen',
  'scale 0–{max}': 'Skala 0–{max}',
  Weights: 'Gewichte',
  'Placeholder split — the real weighting lives inside the formula until the backend exposes it.':
    'Platzhalter-Verteilung — die echte Gewichtung steckt in der Formel, bis das Backend sie offenlegt.',
  'A worked example': 'Ein Rechenbeispiel',
}

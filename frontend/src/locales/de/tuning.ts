// Core area: Tuning — what steers the ranking, shown read-only.
// 'Tuning' itself stays an English loanword, as on the sidebar and the heading.
// Dimension names come from the backend and are never translated.
export const dict: Record<string, string> = {
  Tuning: 'Tuning',
  Controls: 'Steuerung',

  'What the score weighs': 'Was in den Score einfließt',
  'Every paper in this workspace is ranked on these, in this proportion.':
    'Jedes Paper in diesem Workspace wird danach bewertet, in diesem Verhältnis.',
  '{n} of the base': '{n} der Basis',
  '{label} is a threshold, not a weight: below {gate} the score is 0, and at {bonusAt} or above the total is multiplied by {bonus}.':
    '{label} ist ein Schwellenwert, keine Gewichtung: unter {gate} ist der Score 0, ab {bonusAt} wird das Ergebnis mit {bonus} multipliziert.',

  'The dials': 'Die Regler',
  'These weights are managed centrally and apply to every paper in the workspace.':
    'Diese Gewichte werden zentral verwaltet und gelten für jedes Paper im Workspace.',
  'gate {n}': 'Schwelle {n}',
  gate: 'Schwelle',

  'See it applied to a paper:': 'An einem Paper angewendet:',

  'How much each of these counts is not shown: the scoring method has changed, so the breakdown here could not be verified against a scored paper.':
    'Wie stark diese jeweils zählen, wird nicht angezeigt: Die Bewertungsmethode hat sich geändert, daher konnte die Aufschlüsselung nicht anhand eines bewerteten Papers verifiziert werden.',
  'Nothing has been scored in this workspace yet.':
    'In diesem Workspace wurde noch nichts bewertet.',
}

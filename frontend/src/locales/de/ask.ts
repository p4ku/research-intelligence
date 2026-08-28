// Ask — the conversational surface (console, scope toggle, history rail,
// paper palette, streamed answers). Chrome strings only: questions, answers,
// citations, and titles arrive from the backend in English and are never
// translated.
export const dict: Record<string, string> = {
  // page.tsx
  Assistant: 'Assistent',
  'Ask Research Intelligence': 'Research Intelligence fragen',
  // Tab title. Distinct from the nav's 'Ask', which stays an anglicism on purpose.
  'Ask the scanner': 'Scanner fragen',

  // ask.tsx — console chrome
  'Ask console': 'Ask-Konsole',
  Target: 'Ziel',
  'Conversation history': 'Gesprächsverlauf',
  History: 'Verlauf',
  '{n} asked': '{n} gefragt',
  '{title} · full text': '{title} · Volltext',
  'All papers': 'Alle Papers',
  'Ask a question': 'Eine Frage stellen',
  'Ask about {title}…': 'Frage zu {title}…',
  'Ask across all papers…': 'Über alle Papers fragen…',
  Send: 'Senden',

  // scope-toggle.tsx
  'Change paper': 'Paper wechseln',
  'Choose a paper': 'Paper auswählen',

  // history-rail.tsx
  'full text': 'Volltext',
  Today: 'Heute',
  Yesterday: 'Gestern',
  'New conversation': 'Neues Gespräch',
  'Delete conversation': 'Gespräch löschen',
  '{n} turns': '{n} Fragen',
  'Questions you ask are filed here.': 'Gestellte Fragen werden hier abgelegt.',

  // scanner-turn.tsx
  'Asked {time}': 'Gefragt {time}',
  Asked: 'Gefragt',
  'Reading “{title}” · full text': 'Lese „{title}“ · Volltext',
  'Scanning {n} papers': 'Scanne {n} Papers',
  'Target the conversation at this paper': 'Das Gespräch auf dieses Paper ausrichten',
  'Dig in': 'Vertiefen',
  'The answer failed.': 'Die Antwort ist fehlgeschlagen.',
  'p. {n}': 'S. {n}',
  'Verified in source': 'In der Quelle belegt',
  'Fact check': 'Faktencheck',
  passed: 'bestanden',
  flagged: 'auffällig',
  '{n} of {total} claims grounded': '{n} von {total} Aussagen belegt',
  '{n} tokens': '{n} Tokens',

  // paper-palette.tsx
  'Find a paper — title, author, source…': 'Paper finden — Titel, Autor, Quelle…',
  'Find a paper to scope the conversation to': 'Ein Paper wählen, um das Gespräch einzugrenzen',
  'No papers match “{q}” — the workspace holds {n} papers.':
    'Keine Papers passen zu „{q}“ — der Workspace umfasst {n} Papers.',
  '{n} papers scanned': '{n} Papers gescannt',
  navigate: 'navigieren',
  'scope the conversation': 'Gespräch eingrenzen',
}

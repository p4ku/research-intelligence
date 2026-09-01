// Ask — the conversational surface (console, paper picker, history rail,
// streamed answers). Chrome strings only: questions, answers, citations, and
// titles arrive from the backend in English and are never translated.
export const dict: Record<string, string> = {
  // page.tsx
  Assistant: 'Assistent',
  'Ask Research Intelligence': 'Research Intelligence fragen',
  // Tab title. Distinct from the nav's 'Ask', which stays an anglicism on purpose.
  'Ask the scanner': 'Scanner fragen',

  // ask.tsx — console chrome
  'Ask console': 'Ask-Konsole',
  'No paper yet': 'Noch kein Paper',
  'Change paper': 'Paper wechseln',
  'Choose a different paper': 'Ein anderes Paper wählen',
  'One paper at a time': 'Ein Paper nach dem anderen',
  'Every answer is read from a single paper’s full text.':
    'Jede Antwort wird aus dem Volltext eines einzelnen Papers gelesen.',
  'Choose the paper, then ask it anything.': 'Paper wählen, dann alles fragen.',
  'Find a paper': 'Ein Paper finden',
  'Which paper? Type a title, author, or source…':
    'Welches Paper? Titel, Autor oder Quelle tippen…',
  'Ask a question': 'Eine Frage stellen',
  'Ask about this paper…': 'Frage zu diesem Paper…',
  Send: 'Senden',
  Stop: 'Stopp',
  'Jump to latest': 'Zum Neuesten',
  Target: 'Ziel',
  '{title} · full text': '{title} · Volltext',
  'All papers': 'Alle Papers',
  'Conversation history': 'Gesprächsverlauf',
  History: 'Verlauf',
  '{n} asked': '{n} gefragt',

  // paper-picker.tsx
  Papers: 'Papers',
  'No papers match “{q}” — the workspace holds {n} papers.':
    'Keine Papers passen zu „{q}“ — der Workspace umfasst {n} Papers.',
  choose: 'wählen',
  'scope the conversation': 'Gespräch eingrenzen',
  'Top {n} of {total}': 'Top {n} von {total}',
  '{n} of {total}': '{n} von {total}',

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
  'Reading “{title}” · full text': 'Lese „{title}“ · Volltext',
  'Reading the full text…': 'Lese den Volltext…',
  'The answer failed.': 'Die Antwort ist fehlgeschlagen.',
  Stopped: 'Gestoppt',
  'p. {n}': 'S. {n}',
  'Verified in source': 'In der Quelle belegt',
  'Fact check': 'Faktencheck',
  passed: 'bestanden',
  flagged: 'auffällig',
  '{n} of {total} claims grounded': '{n} von {total} Aussagen belegt',
  '{n} tokens': '{n} Tokens',
  // Follow-up questions offered under the newest answer.
  'What does this actually enable?': 'Was ermöglicht das konkret?',
  'What is the strongest counter-argument?': 'Was ist das stärkste Gegenargument?',
  'What would it take to use this at case scale?':
    'Was wäre nötig, um das im Projektmaßstab einzusetzen?',
  'Which claims are weakest?': 'Welche Aussagen sind am schwächsten belegt?',
}

// Ask — the conversational surface (console, paper picker, history rail,
// streamed answers). Chrome strings only: questions, answers, citations, and
// titles arrive from the backend in English and are never translated.
export const dict: Record<string, string> = {
  // page.tsx
  Assistant: 'Assistent',
  'Ask Research Intelligence': 'Research Intelligence fragen',
  // Tab title. The nav's 'Ask' translates via the 'nav' context in chrome.ts.
  'Ask the scanner': 'Scanner fragen',

  // ask.tsx — console chrome
  'Ask console': 'Fragen-Konsole',
  // The console's mono eyebrow; scoped so it can differ from the nav label.
  'console|Ask': 'Fragen',
  'No paper yet': 'Noch kein Paper',
  'Change paper': 'Paper wechseln',
  'Choose a different paper': 'Ein anderes Paper wählen',
  'Ask a paper.': 'Ein Paper fragen.',
  'Find a paper': 'Ein Paper finden',
  'Which paper? Type a title, author, or source…':
    'Welches Paper? Titel, Autor oder Quelle tippen…',
  'Ask a question': 'Eine Frage stellen',
  // Same value in de/papers.ts (the paper-detail chat) — the test enforces that.
  'Ask about this paper…': 'Zu diesem Paper fragen…',
  Send: 'Senden',
  Stop: 'Stopp',
  'Jump to latest': 'Zum Neuesten',
  Target: 'Fokus',
  '{title} · full text': '{title} · Volltext',
  'All papers': 'Alle Papers',
  'Conversation history': 'Gesprächsverlauf',
  History: 'Verlauf',
  // Question counts (history header and per-session rows) share one pair.
  '1 question': '1 Frage',
  '{n} questions': '{n} Fragen',

  // paper-picker.tsx
  Papers: 'Papers',
  'No papers match “{q}” — the workspace holds {n} papers.':
    'Keine Papers passen zu „{q}“ — der Arbeitsbereich umfasst {n} Papers.',
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
  'Delete this conversation?': 'Dieses Gespräch löschen?',
  '"{title}" and every answer in it will be deleted. This cannot be undone.':
    '„{title}“ und alle darin enthaltenen Antworten werden gelöscht. Dies kann nicht rückgängig gemacht werden.',
  Cancel: 'Abbrechen',
  Delete: 'Löschen',
  'Deleting…': 'Wird gelöscht …',
  'Conversation deleted': 'Gespräch gelöscht',
  'History may be out of date.': 'Der Verlauf ist möglicherweise nicht aktuell.',
  Refresh: 'Aktualisieren',
  'Questions you ask are filed here.': 'Gestellte Fragen werden hier abgelegt.',

  // scanner-turn.tsx
  'Asked {time}': 'Gefragt {time}',
  'Reading “{title}” · full text': '„{title}“ wird gelesen · Volltext',
  // Same value in de/papers.ts — the dictionary test enforces that.
  'Reading the full text…': 'Der Volltext wird gelesen…',
  'The answer failed.': 'Die Antwort ist fehlgeschlagen.',
  'The answer stopped part-way through.': 'Die Antwort ist mittendrin abgebrochen.',
  'Ask again': 'Erneut fragen',
  'Answer ready': 'Antwort bereit',
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
  'Loading the assistant': 'Der Assistent wird geladen',
}

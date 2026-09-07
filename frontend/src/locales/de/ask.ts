// Ask — the conversational surface (console, paper picker, history rail,
// streamed answers). Chrome strings only: questions, answers, citations, and
// titles arrive from the backend in English and are never translated.
export const dict: Record<string, string> = {
  // page.tsx
  Assistant: 'Assistent',
  'Ask Research Intelligence': 'Research Intelligence fragen',
  // Tab title. The nav's 'Ask' translates via the 'nav' context in chrome.ts.
  'Ask the scanner': 'Scanner fragen',

  // ask.tsx — canvas chrome
  'New chat': 'Neuer Chat',
  'Recent chats': 'Letzte Chats',
  'What should we look into?': 'Was sollen wir uns ansehen?',
  'Ask anything': 'Frag irgendetwas',
  'Remove this paper': 'Dieses Paper entfernen',

  // tool-menu.tsx — the composer's "+" menu. Only 'Attach a paper' is wired;
  // the rest sit disabled under 'Coming soon'.
  Tools: 'Werkzeuge',
  'Attach a paper': 'Ein Paper anhängen',
  "Scope to one paper's full text": 'Auf den Volltext eines Papers eingrenzen',
  'Coming soon': 'Demnächst',
  'Across papers': 'Über alle Papers',
  'Read the corpus and answer with citations': 'Den Korpus lesen und mit Belegen antworten',
  'Web search': 'Websuche',
  'Look beyond the scanned corpus': 'Über den gescannten Korpus hinaus suchen',
  'Run a scan': 'Einen Scan starten',
  'Fetch new papers for a domain now': 'Jetzt neue Papers für eine Domäne holen',
  'Deep research': 'Tiefenrecherche',
  'Longer, multi-step investigation': 'Längere, mehrstufige Untersuchung',

  // scanner-turn.tsx — the question bubble's scope, shown on hover.
  'Asked {time} · {title} · full text': 'Gefragt {time} · {title} · Volltext',
  'Asked {time} · all papers': 'Gefragt {time} · alle Papers',

  // history-sidecar.tsx
  Recent: 'Zuletzt',

  // ask.tsx — console chrome
  'Ask console': 'Fragen-Konsole',
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
  // Question counts (history header and per-session rows) share one pair.
  '1 question': '1 Frage',
  '{n} questions': '{n} Fragen',

  // paper-picker.tsx
  Papers: 'Papers',
  'No papers match “{q}” — {n} papers to choose from.':
    'Keine Papers passen zu „{q}“ — {n} Papers stehen zur Auswahl.',
  choose: 'wählen',
  'scope the conversation': 'Gespräch eingrenzen',
  'Top {n} of {total}': 'Top {n} von {total}',
  '{n} of {total}': '{n} von {total}',

  // history-rail.tsx
  'full text': 'Volltext',
  Today: 'Heute',
  Yesterday: 'Gestern',
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

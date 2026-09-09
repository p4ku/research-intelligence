// Error copy: the problem-slug sentences from src/lib/bff/problem-copy.ts
// plus the form fallbacks and the workspace/not-found notices.
// problem-copy.test.ts asserts every PROBLEM_COPY value has an entry here.
export const dict: Record<string, string> = {
  // Problem slugs (problem-copy.ts)
  'Check your input and try again.': 'Prüfen Sie Ihre Eingaben und versuchen Sie es erneut.',
  'Your session has ended. Sign in again.':
    'Ihre Sitzung ist abgelaufen. Melden Sie sich erneut an.',
  "You don't have access to this.": 'Sie haben darauf keinen Zugriff.',
  "That wasn't found. It may have been removed.":
    'Das wurde nicht gefunden. Möglicherweise wurde es entfernt.',
  'Something went wrong. Try again.': 'Etwas ist schiefgelaufen. Versuchen Sie es erneut.',
  'This was changed somewhere else. Reload the page and try again.':
    'Dies wurde an anderer Stelle geändert. Laden Sie die Seite neu und versuchen Sie es erneut.',
  'Something went wrong on our side. Try again.':
    'Bei uns ist etwas schiefgelaufen. Versuchen Sie es erneut.',
  "This isn't available yet.": 'Das ist noch nicht verfügbar.',
  "The backend didn't respond. Try again in a moment.":
    'Der Dienst hat nicht geantwortet. Versuchen Sie es gleich noch einmal.',
  'The backend had a problem. Try again in a moment.':
    'Der Dienst hatte ein Problem. Versuchen Sie es gleich noch einmal.',
  'The backend sent something unexpected. Try again in a moment.':
    'Der Dienst hat eine unerwartete Antwort gesendet. Versuchen Sie es gleich noch einmal.',

  // Form fallbacks (settings-form.tsx)
  "Couldn't save your profile. Try again.":
    'Ihr Profil konnte nicht gespeichert werden. Versuchen Sie es erneut.',
  "Couldn't delete this conversation. Try again.":
    'Der Chat konnte nicht gelöscht werden. Versuchen Sie es erneut.',
  "Couldn't open this conversation. Try again.":
    'Der Chat konnte nicht geöffnet werden. Versuchen Sie es erneut.',
  "Couldn't change your password. Try again.":
    'Ihr Passwort konnte nicht geändert werden. Versuchen Sie es erneut.',

  // Workspace notice (workspace-notice.tsx) — a workspace reads as a
  // "Themenfeld" to the analyst; the outage line reuses the chrome's
  // "Nothing was lost…".
  "Couldn't reach the backend.": 'Der Dienst ist nicht erreichbar.',
  'No domains yet': 'Noch keine Themenfelder',
  "You don't have access to any domain yet. Ask an administrator for access.":
    'Sie haben noch keinen Zugriff auf ein Themenfeld. Bitten Sie eine Administratorin oder einen Administrator um Zugriff.',

  // Not-found pages ((sidebar)/not-found.tsx and the root not-found.tsx)
  "We couldn't find that.": 'Das konnten wir nicht finden.',
  'It may have been removed, or the link may be out of date.':
    'Möglicherweise wurde es entfernt, oder der Link ist veraltet.',
  'Go to Papers': 'Zu den Papers',
  'Go to Briefings': 'Zu den Briefings',
  'Go to Dashboard': 'Zur Startseite',

  // Field-level validation we author ourselves (src/lib/bff/settings/schema.ts).
  // Reaches t() through errorsFromSubmit, so no static caller names it.
  'New passwords do not match.': 'Die neuen Passwörter stimmen nicht überein.',
}

// Login page and sign-in errors. The page renders outside the app shell, so
// the server page resolves the language and hands it to the client panel.
export const dict: Record<string, string> = {
  'Sign in': 'Anmelden',
  'Use your email or username and password to continue.':
    'Melden Sie sich mit E-Mail oder Benutzernamen und Passwort an.',
  'Email or username': 'E-Mail oder Benutzername',
  Password: 'Passwort',
  'Signing in…': 'Anmeldung läuft…',
  'Research Intelligence is an internal tool. Access is restricted to authorized accounts.':
    'Research Intelligence ist ein internes Tool. Der Zugriff ist autorisierten Konten vorbehalten.',
  'Your session expired. Please sign in again.':
    'Ihre Sitzung ist abgelaufen. Bitte melden Sie sich erneut an.',
  // Sign-in errors, keyed by the /auth/login error code (see login-panel.tsx).
  'Those credentials did not match. Please try again.':
    'Die Anmeldedaten waren nicht korrekt. Bitte versuchen Sie es erneut.',
  'Enter your email or username and password.':
    'Geben Sie E-Mail oder Benutzernamen und Passwort ein.',
  'The sign-in request was rejected. Reload the page and try again.':
    'Die Anmeldung wurde abgelehnt. Laden Sie die Seite neu und versuchen Sie es erneut.',
  'The service cannot be reached right now. Please try again shortly.':
    'Der Dienst ist derzeit nicht erreichbar. Bitte versuchen Sie es in Kürze erneut.',
  'The sign-in could not be processed (HTTP {status}).':
    'Die Anmeldung konnte nicht verarbeitet werden (HTTP {status}).',
}

// Where the Django backend lives, as seen from the Next.js server.
//
// In production the frontend and backend share one hostname on Cloud Foundry,
// path-routed by Gorouter; BACKEND_INTERNAL_URL is the public host (or the
// container-to-container address if that network policy exists). Locally it
// points at `manage.py runserver` or the compose `api` service.

export function backendUrl(): string {
  const explicit = process.env.BACKEND_INTERNAL_URL
  const fromPublic = process.env.NEXT_PUBLIC_API_URL?.replace(/\/api\/?$/, '')
  return (explicit || fromPublic || 'http://localhost:8000').replace(/\/+$/, '')
}

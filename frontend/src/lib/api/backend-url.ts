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

/**
 * Check if a fetch rejection was caused by a transient DNS/network failure
 * (e.g. EAI_AGAIN DNS lookup timeout, ECONNRESET, connection timeout).
 */
export function isTransientNetworkError(error: unknown): boolean {
  if (!error) return false
  const cause = (error as { cause?: { code?: string; message?: string } })?.cause
  const code = cause?.code ?? (error as { code?: string })?.code
  if (
    code &&
    [
      'EAI_AGAIN',
      'ECONNRESET',
      'ETIMEDOUT',
      'UND_ERR_CONNECT_TIMEOUT',
      'ENOTFOUND',
      'EPIPE',
    ].includes(code)
  ) {
    return true
  }
  const msg = String(cause?.message || (error as Error)?.message || '')
  return (
    msg.includes('EAI_AGAIN') ||
    msg.includes('ECONNRESET') ||
    msg.includes('ETIMEDOUT') ||
    msg.includes('fetch failed')
  )
}

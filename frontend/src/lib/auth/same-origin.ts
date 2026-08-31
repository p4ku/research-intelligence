/** Same-site guard for state-changing requests (login CSRF and BFF writes). */
import type { NextRequest } from 'next/server'

export function isSameOrigin(request: NextRequest): boolean {
  const site = request.headers.get('sec-fetch-site')
  if (site && site !== 'same-origin' && site !== 'none') return false
  const origin = request.headers.get('origin')
  const host = request.headers.get('host')
  if (origin && host) {
    try {
      return new URL(origin).host === host
    } catch {
      return false
    }
  }
  return true
}

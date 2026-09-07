/**
 * Bridge for server components calling BFF services directly: a 401 problem
 * (Django rejected the session) sends the user through the logout flow, the
 * way `apiJson`'s redirect mode did; everything else reaches `error.tsx`.
 * Server-only.
 */
import 'server-only'

import { redirect } from 'next/navigation'
import { isUnauthenticated } from './problem'

export async function forPage<T>(work: Promise<T>): Promise<T> {
  try {
    return await work
  } catch (error) {
    if (isUnauthenticated(error)) {
      redirect('/auth/logout?reason=expired')
    }
    throw error
  }
}

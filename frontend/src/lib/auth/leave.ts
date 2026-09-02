/**
 * The one place client code leaves the authed tree. Both exits are deliberate
 * document navigations, not router transitions: the session cookies are
 * httpOnly (only /auth/logout can drop them) and the server tree must
 * re-render without the session — the client router can do neither, which is
 * why the `no-location-assign-relative-destination` disables below are
 * intentional. Client-safe; both entry points no-op without a window.
 */

/**
 * Once a navigation is committed nothing else may file another: several
 * widgets can 401 in the same tick, and a deliberate sign-out clears the
 * cookies before navigating, which 401s any in-flight call — without the
 * guard that race would repaint a sign-out as "your session expired".
 */
let leaving = false

function beginLeave(): boolean {
  if (typeof window === 'undefined' || leaving) return false
  leaving = true
  return true
}

if (typeof window !== 'undefined') {
  // A bfcache restore (back button after signing out) revives this module
  // with `leaving` still true — reset it or the page can never leave again.
  window.addEventListener('pageshow', (event) => {
    if (event.persisted) leaving = false
  })
}

/**
 * Django rejected the session: hand over to /auth/logout, carrying where the
 * user was so sign-in can put them back. The route re-validates `next`
 * server-side (safeNext); this stays dumb on purpose.
 */
export function sessionExpired(): void {
  if (!beginLeave()) return
  const next = window.location.pathname + window.location.search
  const query = new URLSearchParams({ reason: 'expired', next })
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- deliberate document navigation, see module comment
  window.location.assign(`/auth/logout?${query}`)
}

/**
 * Sign out with a guaranteed outcome on every path. The POST drops the
 * cookies; if it fails (offline, 403, 5xx, hang), fall back to a same-origin
 * GET *navigation* to the same route — it passes the sec-fetch-site guard and
 * clears the cookies server-side, so no failure leaves the user signed in.
 * The fetch must follow redirects (default): `redirect: 'manual'` would make
 * the 303 an opaque `!res.ok` and send every success down the fallback.
 */
export async function performSignOut(): Promise<void> {
  if (!beginLeave()) return
  try {
    const res = await fetch('/auth/logout', {
      method: 'POST',
      signal: AbortSignal.timeout(8000),
    })
    if (!res.ok) throw new Error(String(res.status))
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- deliberate document navigation, see module comment
    window.location.assign('/?reason=signed-out')
  } catch {
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- deliberate document navigation, see module comment
    window.location.assign('/auth/logout?reason=signed-out')
  }
}

/** Test-only: bun runs every test in one process, so the guard must reset. */
export function resetLeaveGuardForTests(): void {
  leaving = false
}

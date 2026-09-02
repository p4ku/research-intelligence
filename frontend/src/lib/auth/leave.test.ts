import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import { performSignOut, resetLeaveGuardForTests, sessionExpired } from './leave'

// The module reads `window.location` and calls `fetch`; both are stubbed on
// globalThis per test and restored after (bun runs all tests in one process).
const realWindow = (globalThis as Record<string, unknown>).window
const realFetch = globalThis.fetch

let assign: ReturnType<typeof mock>

function stubWindow(pathname = '/papers/42', search = '?x=1&y=2') {
  assign = mock(() => {})
  ;(globalThis as Record<string, unknown>).window = {
    location: { pathname, search, assign },
    addEventListener: () => {},
  }
}

function stubFetch(impl: () => Promise<Response>) {
  globalThis.fetch = mock(impl) as unknown as typeof fetch
}

beforeEach(() => {
  resetLeaveGuardForTests()
  stubWindow()
})

afterEach(() => {
  ;(globalThis as Record<string, unknown>).window = realWindow
  globalThis.fetch = realFetch
})

describe('sessionExpired', () => {
  test('navigates to the logout route carrying reason and the encoded location', () => {
    sessionExpired()
    expect(assign).toHaveBeenCalledTimes(1)
    const url = assign.mock.calls[0]?.[0] as string
    expect(url.startsWith('/auth/logout?')).toBe(true)
    const params = new URLSearchParams(url.split('?')[1])
    expect(params.get('reason')).toBe('expired')
    expect(params.get('next')).toBe('/papers/42?x=1&y=2')
  })

  test('parallel 401s collapse to one navigation', () => {
    sessionExpired()
    sessionExpired()
    expect(assign).toHaveBeenCalledTimes(1)
  })

  test('without a window (server) it neither throws nor navigates', () => {
    delete (globalThis as Record<string, unknown>).window
    expect(() => sessionExpired()).not.toThrow()
    expect(assign).toHaveBeenCalledTimes(0)
  })
})

describe('performSignOut', () => {
  test('successful POST navigates to the signed-out notice, exactly once', async () => {
    stubFetch(() => Promise.resolve(new Response(null, { status: 200 })))
    await performSignOut()
    expect(assign).toHaveBeenCalledTimes(1)
    expect(assign).toHaveBeenCalledWith('/?reason=signed-out')
  })

  test('rejected fetch (offline) still leaves via the GET fallback', async () => {
    stubFetch(() => Promise.reject(new TypeError('Failed to fetch')))
    await performSignOut()
    expect(assign).toHaveBeenCalledWith('/auth/logout?reason=signed-out')
  })

  test('a 403 must not strand the user signed in — GET fallback', async () => {
    stubFetch(() => Promise.resolve(new Response(null, { status: 403 })))
    await performSignOut()
    expect(assign).toHaveBeenCalledWith('/auth/logout?reason=signed-out')
  })

  test('a sign-out already underway blocks a racing sessionExpired', async () => {
    // The POST clears the cookies, so in-flight calls 401 mid-sign-out; the
    // guard keeps the deliberate sign-out from being repainted as expiry.
    let settle: (res: Response) => void = () => {}
    stubFetch(() => new Promise<Response>((resolve) => (settle = resolve)))
    const pending = performSignOut()
    sessionExpired()
    settle(new Response(null, { status: 200 }))
    await pending
    expect(assign).toHaveBeenCalledTimes(1)
    expect(assign).toHaveBeenCalledWith('/?reason=signed-out')
  })

  test('after sessionExpired a sign-out does nothing further', async () => {
    stubFetch(() => Promise.resolve(new Response(null, { status: 200 })))
    sessionExpired()
    await performSignOut()
    expect(assign).toHaveBeenCalledTimes(1)
  })
})

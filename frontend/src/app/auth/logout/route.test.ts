import { describe, expect, test } from 'bun:test'
import { NextRequest } from 'next/server'
import { GET, POST } from './route'

const BASE = 'http://localhost:3000/auth/logout'

// The three session cookies must be cleared on every legitimate sign-out —
// and the stars stub store with them, so the next account on a shared
// browser does not inherit the previous one's stars.
// `Secure` is deliberately not asserted: the test env is not production.
const AUTH_COOKIES = ['sri_access', 'sri_refresh', 'sri_user', 'rs-stars']

function expectCookiesCleared(res: Response) {
  const setCookies = res.headers.getSetCookie()
  expect(setCookies).toHaveLength(AUTH_COOKIES.length)
  for (const name of AUTH_COOKIES) {
    const header = setCookies.find((c) => c.startsWith(`${name}=`))
    expect(header).toContain('Max-Age=0')
  }
}

function locationParams(res: Response): URLSearchParams {
  const location = res.headers.get('location') ?? ''
  return new URLSearchParams(location.split('?')[1] ?? '')
}

describe('GET /auth/logout', () => {
  test('forwards reason and a valid next to the login page, cookies cleared', async () => {
    const res = await GET(new NextRequest(`${BASE}?reason=expired&next=%2Fask`))
    expect(res.status).toBe(303)
    expect(res.headers.get('location')).toBe('/?reason=expired&next=%2Fask')
    expectCookiesCleared(res)
  })

  test('bare visit redirects to exactly /', async () => {
    const res = await GET(new NextRequest(BASE))
    expect(res.headers.get('location')).toBe('/')
    expectCookiesCleared(res)
  })

  test('an off-origin next never survives', async () => {
    // '/\t/evil.com' arrives as next=%2F%09%2Fevil.com and decodes back to a
    // real tab, which the URL parser would strip at the sink — must not pass.
    for (const evil of ['https://evil.example', '//evil.com', '/\t/evil.com']) {
      const res = await GET(
        new NextRequest(`${BASE}?reason=expired&next=${encodeURIComponent(evil)}`),
      )
      expect(locationParams(res).get('next')).toBeNull()
      expect(locationParams(res).get('reason')).toBe('expired')
    }
  })

  test('next to the default landing or into /auth is omitted', async () => {
    for (const next of ['%2Fdashboard', '%2Fauth%2Flogout']) {
      const res = await GET(new NextRequest(`${BASE}?next=${next}`))
      expect(res.headers.get('location')).toBe('/')
    }
  })

  test('an unknown reason is dropped; a valid next still carries', async () => {
    const res = await GET(new NextRequest(`${BASE}?reason=pwned&next=%2Fask`))
    expect(res.headers.get('location')).toBe('/?next=%2Fask')
  })

  test('cross-site navigation clears nothing and honours no params', async () => {
    const res = await GET(
      new NextRequest(`${BASE}?reason=expired&next=%2Fask`, {
        headers: { 'sec-fetch-site': 'cross-site' },
      }),
    )
    expect(res.status).toBe(303)
    expect(res.headers.get('location')).toBe('/')
    expect(res.headers.getSetCookie()).toHaveLength(0)
  })
})

describe('POST /auth/logout', () => {
  test('same-origin sign-out clears the cookies', async () => {
    const res = await POST(new NextRequest(BASE, { method: 'POST' }))
    expect(res.status).toBe(303)
    expect(res.headers.get('location')).toBe('/')
    expectCookiesCleared(res)
  })

  test('cross-site POST is refused', async () => {
    const res = await POST(
      new NextRequest(BASE, {
        method: 'POST',
        headers: { 'sec-fetch-site': 'cross-site' },
      }),
    )
    expect(res.status).toBe(403)
    expect(res.headers.getSetCookie()).toHaveLength(0)
  })
})

import { afterEach, describe, expect, test } from 'bun:test'
import { authCookieOptions, secureCookies } from './cookies'

const { NODE_ENV, SITE_URL } = process.env

function env(nodeEnv: string | undefined, siteUrl: string | undefined) {
  // NODE_ENV is readonly in the Next types but writable at runtime.
  ;(process.env as Record<string, string | undefined>).NODE_ENV = nodeEnv
  ;(process.env as Record<string, string | undefined>).SITE_URL = siteUrl
}

afterEach(() => env(NODE_ENV, SITE_URL))

describe('secureCookies', () => {
  test('https origin in production → Secure', () => {
    env('production', 'https://sri-prod.apps.01.cf.eu01.onstackit.cloud')
    expect(secureCookies()).toBe(true)
  })

  test('plain-http origin → not Secure, or the browser drops the cookies', () => {
    env('production', 'http://localhost:3000')
    expect(secureCookies()).toBe(false)
  })

  test('unset SITE_URL in production fails safe', () => {
    env('production', undefined)
    expect(secureCookies()).toBe(true)
  })

  test('development is never Secure', () => {
    env('development', 'https://sri-prod.apps.01.cf.eu01.onstackit.cloud')
    expect(secureCookies()).toBe(false)
  })

  test('an https SITE_URL cannot be downgraded by request headers', () => {
    // Regression guard: the flag is derived from server config only. Nothing
    // a client sends (X-Forwarded-Proto included) is consulted here.
    env('production', 'https://sri.soinventive.co.uk')
    expect(secureCookies()).toBe(true)
  })
})

describe('authCookieOptions', () => {
  test('carries the session hardening flags', () => {
    env('production', 'https://sri.soinventive.co.uk')
    expect(authCookieOptions()).toEqual({
      httpOnly: true,
      sameSite: 'lax',
      path: '/',
      secure: true,
      maxAge: 86400,
    })
  })
})

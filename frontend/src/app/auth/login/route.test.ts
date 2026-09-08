import { describe, expect, test } from 'bun:test'
import { NextRequest } from 'next/server'
import { POST } from './route'

const BASE = 'http://localhost:3000/auth/login'

// A body that is not an object used to reach `body.identifier?.trim()` and
// throw, so the handler answered 500 with no code — the login panel then
// reports "unreachable" for what is really a bad request. Every case below
// must stop inside the handler, before the upstream fetch.
const post = (body: string) =>
  POST(
    new NextRequest(BASE, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body,
    }),
  )

async function code(res: Response): Promise<unknown> {
  return ((await res.json()) as { code?: unknown }).code
}

describe('POST /auth/login', () => {
  test('a JSON body that is not an object is a bad request, not a 500', async () => {
    for (const body of ['null', '"x"', '3']) {
      const res = await post(body)
      expect(res.status).toBe(400)
      expect(await code(res)).toBe('invalid-request')
    }
  })

  test('an unparseable body is a bad request', async () => {
    const res = await post('{')
    expect(res.status).toBe(400)
    expect(await code(res)).toBe('invalid-request')
  })

  test('an object without usable credentials asks for them', async () => {
    for (const body of ['[]', '{"identifier":123,"password":"x"}', '{"identifier":"  "}']) {
      const res = await post(body)
      expect(res.status).toBe(400)
      expect(await code(res)).toBe('missing-credentials')
    }
  })

  test('cross-site is refused before the body is read', async () => {
    const res = await POST(
      new NextRequest(BASE, {
        method: 'POST',
        headers: { 'sec-fetch-site': 'cross-site' },
        body: 'null',
      }),
    )
    expect(res.status).toBe(403)
    expect(await code(res)).toBe('cross-site')
  })
})

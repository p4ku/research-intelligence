import { clearAuthCookies } from '@/lib/auth/cookies'
import { NextResponse } from 'next/server'

// Django has no logout endpoint (no token blacklist), so signing out is
// purely dropping the cookies. GET exists so server code can `redirect()`
// here when Django rejects a token mid-session (?reason=expired); the
// relative Location keeps the scheme/host the browser already uses.

function signOut() {
  const res = new NextResponse(null, { status: 303, headers: { Location: '/' } })
  clearAuthCookies(res.cookies)
  return res
}

export async function POST() {
  return signOut()
}

export async function GET() {
  return signOut()
}

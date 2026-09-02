import { authCookieOptions, encodeUserCookie, toCookieUser, USER_COOKIE } from '@/lib/auth/cookies'
import { bff } from '@/lib/bff/core/handler'
import { parseBody } from '@/lib/bff/core/validate'
import { profileUpdate } from '@/lib/bff/settings/schema'
import { settings } from '@/lib/bff/settings/service'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

export const GET = bff(null, async () => Response.json(await settings.profile()))

export const PATCH = bff(null, async (request) => {
  const update = await parseBody(profileUpdate, request)
  const profile = await settings.updateProfile(update)
  // Keep the display cookie (name/email in the sidebar) in step.
  const res = NextResponse.json(profile)
  res.cookies.set(USER_COOKIE, encodeUserCookie(toCookieUser(profile)), authCookieOptions())
  return res
})

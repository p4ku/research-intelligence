import { bff } from '@/lib/bff/core/handler'
import { parseBody } from '@/lib/bff/core/validate'
import { passwordChange } from '@/lib/bff/settings/schema'
import { settings } from '@/lib/bff/settings/service'

export const dynamic = 'force-dynamic'

export const POST = bff(null, async (request) => {
  const change = await parseBody(passwordChange, request)
  const message = await settings.changePassword(change)
  return Response.json({ message })
})

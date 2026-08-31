import { bff } from '@/lib/bff/core/handler'
import { parseBody, parseQuery } from '@/lib/bff/core/validate'
import { preferences, preferencesQuery } from '@/lib/bff/settings/schema'
import { settings } from '@/lib/bff/settings/service'

export const dynamic = 'force-dynamic'

export const GET = bff('preferences', async (request) => {
  const { workspace_id } = parseQuery(preferencesQuery, request.nextUrl)
  return Response.json(await settings.getPreferences(workspace_id))
})

export const PUT = bff('preferences', async (request) => {
  const { workspace_id } = parseQuery(preferencesQuery, request.nextUrl)
  const next = await parseBody(preferences, request)
  return Response.json(await settings.setPreferences(workspace_id, next))
})

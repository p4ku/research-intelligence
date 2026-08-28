import { bff } from '@/lib/bff/core/handler'
import { bffStatus } from '@/lib/bff/status/service'

export const dynamic = 'force-dynamic'

export const GET = bff(null, async () => Response.json(await bffStatus()))

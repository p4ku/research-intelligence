import { editionQueryOf } from '@/lib/bff/briefings/edition-query'
import { screeningLogFilename } from '@/lib/bff/briefings/export'
import { assertDate, briefings } from '@/lib/bff/briefings/service'
import { bff } from '@/lib/bff/core/handler'
import { problem } from '@/lib/bff/core/problem'
import { workspaces } from '@/lib/bff/workspaces/service'
import { makeT } from '@/lib/i18n'
import { getLang } from '@/lib/i18n-server'
import { renderScreeningLog } from './document'

export const dynamic = 'force-dynamic'

/**
 * The screening log as a PDF: the edition the JSON route serves, set as a
 * document (funnel, then every exclusion with its reasoning) and sent as an
 * attachment named for the domain and the day. The domain's name is a
 * courtesy — a failed workspaces read leaves it to the edition.
 */
export const GET = bff('briefings', async (request, ctx) => {
  const { date } = await ctx.params
  const { workspace_id, run_id } = editionQueryOf(request)
  const lang = await getLang()
  const t = makeT(lang)
  const [found, all] = await Promise.all([
    briefings.findByDate(assertDate(date), lang, workspace_id, run_id),
    workspaces.listAll().catch(() => []),
  ])
  if (!found) throw problem('not-found', { detail: 'No briefing for that day.' })
  const domain = all.find((ws) => ws.id === found.workspace_id)?.name ?? found.workspace_name
  const pdf = await renderScreeningLog({ edition: found, domain, lang, t, exportedAt: new Date() })
  const filename = screeningLogFilename(t('Screening log'), domain, found.date)
  return new Response(new Uint8Array(pdf), {
    headers: {
      'content-type': 'application/pdf',
      'content-disposition': `attachment; filename="${filename}"`,
    },
  })
})

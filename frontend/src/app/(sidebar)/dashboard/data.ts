import 'server-only'

import { briefings } from '@/lib/bff/briefings/service'
import { papers as papersService } from '@/lib/bff/papers/service'
import { runs as runsService } from '@/lib/bff/pipeline-runs/service'
import type { Lang, T } from '@/lib/i18n'
import { isPassed } from '@/lib/papers/map'
import { byValueDesc } from '@/lib/papers/select'
import { cache } from 'react'

/**
 * Per-request accessors for the dashboard's streamed sections. Each section
 * awaits only what it renders; `cache()` de-duplicates across sections (the
 * eyebrow, the domain badge and the paper list all need the latest run).
 * "Today" is the newest completed run in any of the user's domains; which
 * domain that is comes from the run itself.
 */

export const latestRun = cache(
  async () => (await runsService.listEverywhere('completed'))[0] ?? null,
)

export const runPapers = cache(async () => {
  const latest = await latestRun()
  const scored = latest ? await papersService.listAll(latest.workspace_id) : null
  // The latest completed run and the papers it surfaced: the dashboard claims
  // no more than the list below shows.
  const papers =
    latest && scored
      ? scored.papers
          .filter((p) => p.pipeline_run_id === latest.id && isPassed(p.screening_status))
          .sort((a, b) => byValueDesc(a.signal_score, b.signal_score))
      : []
  return { latest, workspace: scored?.workspace ?? null, papers }
})

export const editionToday = cache(async (lang: Lang) => {
  const latest = await latestRun()
  if (!latest) return null
  const editions = await briefings.listAll(latest.workspace_id, lang)
  // The edition this run produced. Same-day reruns collapse to the newest,
  // which `latest` is, so the fallback only covers a list that has moved on.
  return editions.find((e) => e.run_id === latest.id) ?? editions[0] ?? null
})

/** The funnel's static copy — shared by the loaded band and its skeleton. */
export function funnelCopy(t: T) {
  return [
    { label: t('Screened'), sub: t('matched the focus fields') },
    { label: t('Included'), sub: t('cleared the signal bar') },
    { label: t('In the briefing'), sub: t('listed below') },
  ]
}

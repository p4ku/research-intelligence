import { Card } from '@/components/scanner-ui'
import { briefings } from '@/lib/bff/briefings/service'
import { forPage } from '@/lib/bff/core/page'
import type { Lang, T } from '@/lib/i18n'
import type { WorkspaceSummary } from '@/lib/papers/types'
import { EditionBrowser, type BrowserEdition } from './edition-browser'

/** The archive behind its Suspense boundary: every edition of every domain, or the empty card. */
export async function EditionsSection({
  workspaces,
  lang,
  t,
}: {
  workspaces: WorkspaceSummary[]
  lang: Lang
  t: T
}) {
  const editions = await forPage(briefings.listEverywhere(lang))
  const domainOf = new Map(workspaces.map((ws) => [ws.id, ws.name]))

  if (editions.length === 0) {
    return (
      <Card>
        <p className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
          {t('No completed runs yet.')}
        </p>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          {t('Once a pipeline run completes in any of your domains, its briefing appears here.')}
        </p>
      </Card>
    )
  }

  const browserEditions: BrowserEdition[] = editions.map((e) => ({
    runId: e.run_id,
    workspaceId: e.workspace_id,
    domain: domainOf.get(e.workspace_id) ?? '—',
    date: e.date,
    title: e.title,
    inBrief: e.in_brief,
    proseSource: e.in_brief_source,
    funnel: {
      screened: e.funnel.fetched,
      included: e.funnel.passed_screening,
      inBriefing: e.funnel.surfaced,
    },
    papers: e.papers.map((p) => ({ id: p.id, title: p.title, signal: p.signal_score })),
  }))

  return <EditionBrowser editions={browserEditions} lang={lang} />
}

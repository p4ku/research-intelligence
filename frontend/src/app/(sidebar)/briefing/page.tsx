import { Card, PageHeader } from '@/components/scanner-ui'
import { WorkspaceNotice } from '@/components/workspace-notice'
import { briefings } from '@/lib/bff/briefings/service'
import { forPage } from '@/lib/bff/core/page'
import { getLang, getT } from '@/lib/i18n-server'
import { getWorkspaceState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { EditionBrowser, type BrowserEdition } from './edition-browser'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT()
  return { title: t('Briefings') }
}

// /briefing is the archive as a reading room: the dashboard carries today's
// briefing, and every edition lives here — search on top, the selected brief
// on the left, the history rail on the right. One edition per completed
// pipeline run; each has a permalink at /briefing/[date].

export default async function BriefingPage() {
  const [t, lang, state] = await Promise.all([getT(), getLang(), getWorkspaceState()])
  const editions = state.kind === 'ok' ? await forPage(briefings.listAll(state.ws.id, lang)) : []

  if (state.kind !== 'ok' || editions.length === 0) {
    return (
      <div className="space-y-8">
        <PageHeader eyebrow={t('Daily briefings')} title={t('Briefings')} />
        {state.kind !== 'ok' ? (
          <WorkspaceNotice state={state} />
        ) : (
          <Card>
            <p className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
              {t('No completed runs yet.')}
            </p>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              {t('Once a pipeline run completes in this workspace, its briefing appears here.')}
            </p>
          </Card>
        )}
      </div>
    )
  }

  const browserEditions: BrowserEdition[] = editions.map((e) => ({
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

  return (
    <div className="space-y-8">
      <PageHeader eyebrow={t('Daily briefings')} title={t('Briefings')} />
      <EditionBrowser editions={browserEditions} lang={lang} />
    </div>
  )
}

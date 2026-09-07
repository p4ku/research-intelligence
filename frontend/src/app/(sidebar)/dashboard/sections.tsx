import { Card, SectionLabel } from '@/components/scanner-ui'
import type { Edition } from '@/lib/bff/briefings/schema'
import { forPage } from '@/lib/bff/core/page'
import type { PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import type { Lang, T } from '@/lib/i18n'
import { editionHref } from '../briefing/format'
import { currentRun, editionFor, recentRuns } from './data'
import { formatAuthors, formatClock, formatDay, periodLabel } from './format'
import { HomeLinks, type HomePaper } from './home-ui'
import { Ledger, type HomeRow, type RowStatus } from './ledger'
import { LiveRefresh } from './live-refresh'
import { Masthead, type MastheadLead } from './masthead'
import { RunCard, type RunDomain } from './run-card'

/**
 * Home's streamed sections: one async Server Component per Suspense
 * boundary, each awaiting only its own data (through `forPage`, so a 401
 * still lands on /auth/logout). Each returns a single root element — the
 * page wraps it in a <ViewTransition> pair with its skeleton.
 */

/** How many of the briefing's strongest papers Home shows. */
const TOP = 3

function topPapers(edition: Edition): HomePaper[] {
  return edition.papers.slice(0, TOP).map((p) => ({
    id: p.id,
    title: p.title,
    authors: formatAuthors(p.authors),
    score: p.signal_score,
  }))
}

/** The spec's three labels: Current, Processing, Failed; other completed rows carry none. */
function rowStatus(run: PipelineRun, currentId: string | null): RowStatus {
  switch (run.status) {
    case 'completed':
      // Nothing cleared screening: there is no briefing to be current.
      if (run.total_papers_passed_screening === 0) return 'empty'
      return run.id === currentId ? 'current' : 'done'
    case 'running':
    case 'pending':
      return 'processing'
    case 'failed':
    case 'aborted':
      return 'failed'
  }
}

/** The day a completed run finished (UTC), which is also its edition's date. */
function completionDay(run: PipelineRun): string {
  return (run.completed_at ?? run.run_date).slice(0, 10)
}

/** The Current briefing read first. Nothing until a run has completed. */
export async function MastheadSection({ t, lang }: { t: T; lang: Lang }) {
  const current = await forPage(currentRun())
  if (!current) return null
  const edition = await forPage(editionFor(current.workspace_id, current.id, lang))
  const lead: MastheadLead = {
    domain: current.workspace_name,
    period: periodLabel(current, t, lang),
    generated: formatDay(completionDay(current), lang),
    // No edition (the corpus could not be read): nothing to link to.
    href: edition ? editionHref(edition.date, current.workspace_id) : null,
    inBrief: edition?.in_brief ?? null,
    template: edition?.in_brief_source === 'template',
    // The run's own counters, the same numbers the ledger's Papers column
    // shows — one source, so the two never disagree.
    screened: current.total_papers_fetched,
    included: current.total_papers_passed_screening,
    top: edition ? topPapers(edition) : [],
  }
  return <Masthead lead={lead} t={t} />
}

/**
 * Recent Briefings beside Start New Briefing. One boundary: the form's
 * disabled state depends on the same list the table shows.
 */
export async function LedgerSection({
  t,
  lang,
  domains,
  today,
}: {
  t: T
  lang: Lang
  domains: RunDomain[]
  today: string
}) {
  const [items, current] = await forPage(Promise.all([recentRuns(lang), currentRun()]))
  const rows: HomeRow[] = items.map(({ run, edition }) => {
    const status = rowStatus(run, current?.id ?? null)
    const completed = run.status === 'completed'
    return {
      id: run.id,
      domain: run.workspace_name,
      status,
      period: periodLabel(run, t, lang),
      generated: completed ? formatDay(completionDay(run), lang) : null,
      startedClock: run.started_at ? formatClock(run.started_at) : null,
      // Django stamps completed_at on failure and abort alike.
      failedDay:
        status === 'failed'
          ? formatDay(run.completed_at ?? run.started_at ?? run.run_date, lang)
          : null,
      papers: completed ? run.total_papers_passed_screening : null,
      retry:
        status === 'failed' && run.retryable
          ? {
              workspace_id: run.workspace_id,
              start_date: run.period_start ?? undefined,
              end_date: run.period_end ?? undefined,
              lookback_days: run.lookback_days ?? undefined,
            }
          : null,
      brief:
        edition && status !== 'empty'
          ? {
              href: editionHref(edition.date, run.workspace_id),
              inBrief: edition.in_brief,
              screened: run.total_papers_fetched,
              included: run.total_papers_passed_screening,
              top: topPapers(edition),
            }
          : null,
    }
  })
  const processing = rows.find((row) => row.status === 'processing') ?? null

  return (
    <div className="grid gap-8 lg:grid-cols-3">
      <div className="min-w-0 lg:col-span-2">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <SectionLabel size="sm">{t('Recent briefings')}</SectionLabel>
          <HomeLinks t={t} />
        </div>
        <div className="mt-4">
          {rows.length === 0 ? (
            <Card>
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                {t('No briefings have been generated yet.')}
              </p>
            </Card>
          ) : (
            <Ledger rows={rows} busy={processing !== null} />
          )}
        </div>
      </div>
      <aside className="lg:col-span-1">
        <RunCard domains={domains} processing={processing?.domain ?? null} today={today} />
      </aside>
      <LiveRefresh
        processingIds={rows.filter((row) => row.status === 'processing').map((row) => row.id)}
      />
    </div>
  )
}

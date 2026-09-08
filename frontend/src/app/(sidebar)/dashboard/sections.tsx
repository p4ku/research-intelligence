import { Card, SectionLabel } from '@/components/scanner-ui'
import type { Edition } from '@/lib/bff/briefings/schema'
import { editionDate } from '@/lib/bff/briefings/select'
import { forPage } from '@/lib/bff/core/page'
import type { PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import type { Lang, T } from '@/lib/i18n'
import { paperHref } from '@/lib/papers/href'
import { editionHref } from '../briefing/format'
import { currentRun, inFlightRuns, recentBriefings } from './data'
import { clockStamp, formatAuthors, formatClock, formatDay, periodLabel } from './format'
import { HomeLinks, type HomePaper } from './home-ui'
import { Ledger, type HomeRow, type RowStatus } from './ledger'
import { LiveRefresh } from './live-refresh'
import { RunCard, type RunDomain } from './run-card'

/**
 * Home's streamed section: an async Server Component behind one Suspense
 * boundary, awaiting only its own data (through `forPage`, so a 401 still
 * lands on /auth/logout). It returns a single root element — the page wraps
 * it in a <ViewTransition> pair with its skeleton. The masthead section
 * that used to sit above it was hidden on 7 Sep 2026 (see page.tsx).
 */

/** How many of the briefing's strongest papers Home shows. */
const TOP = 3

function topPapers(edition: Edition): HomePaper[] {
  return edition.papers.slice(0, TOP).map((p) => ({
    id: p.id,
    href: paperHref(p.id, { runId: edition.run_id }),
    title: p.title,
    authors: formatAuthors(p.authors),
    score: p.signal_score,
  }))
}

/**
 * The spec's three labels: Current, Processing, Failed; other completed rows
 * carry none. A completed run here always has a briefing (data.ts keeps the
 * rest out), so Current is simply the newest completed run — and unset when
 * that run briefed nothing, as in the archive.
 */
function rowStatus(run: PipelineRun, currentId: string | null): RowStatus {
  switch (run.status) {
    case 'completed':
      return run.id === currentId ? 'current' : 'done'
    case 'running':
    case 'pending':
      return 'processing'
    case 'failed':
    case 'aborted':
      return 'failed'
  }
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
  const [items, current, inFlight] = await forPage(
    Promise.all([recentBriefings(lang), currentRun(), inFlightRuns()]),
  )
  const rows: HomeRow[] = items.map(({ run, edition }) => {
    const status = rowStatus(run, current?.id ?? null)
    const completed = run.status === 'completed'
    return {
      id: run.id,
      domain: run.workspace_name,
      status,
      period: periodLabel(run, t, lang),
      generated: completed ? formatDay(editionDate(run), lang) : null,
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
      brief: edition
        ? {
            href: editionHref(edition.date, run.workspace_id, { runId: run.id }),
            inBrief: edition.in_brief,
            screened: run.total_papers_fetched,
            included: run.total_papers_passed_screening,
            top: topPapers(edition),
          }
        : null,
    }
  })
  // A domain that briefed twice in a day has two rows that would read the
  // same (period and day match): those, and only those, carry the clock.
  const perDay = new Map<string, number>()
  const dayOf = (run: PipelineRun) => `${run.workspace_id}|${editionDate(run)}`
  for (const { run } of items) {
    if (run.status === 'completed') perDay.set(dayOf(run), (perDay.get(dayOf(run)) ?? 0) + 1)
  }
  items.forEach(({ run }, i) => {
    if (run.status === 'completed' && run.completed_at && (perDay.get(dayOf(run)) ?? 0) > 1) {
      rows[i]!.stamp = clockStamp(run.completed_at)
    }
  })
  // From every run in flight, not the rows: one may sit below the fifth briefing.
  const processing = inFlight[0] ?? null

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
        <RunCard domains={domains} processing={processing?.workspace_name ?? null} today={today} />
      </aside>
      <LiveRefresh processingIds={inFlight.map((run) => run.id)} />
    </div>
  )
}

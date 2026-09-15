import { Card, SectionLabel } from '@/components/scanner-ui'
import type { Edition } from '@/lib/bff/briefings/schema'
import { forPage } from '@/lib/bff/core/page'
import type { InFlightRun } from '@/lib/bff/pipeline-runs/admission'
import type { PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import type { Lang, T } from '@/lib/i18n'
import { paperHref } from '@/lib/papers/href'
import { editionHref } from '../briefing/format'
import { currentRun, inFlightRuns, recentBriefings } from './data'
import { clockStamp, formatAuthors, formatClock, formatDay, periodLabel } from './format'
import { HomeGrid, HomeLinks, type HomePaper } from './home-ui'
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
    const instant = run.completed_at ?? edition?.generated_at ?? run.started_at
    const day = instant ? formatDay(instant, lang) : formatDay(edition?.date ?? run.run_date, lang)
    const stamp = instant ? clockStamp(instant, lang) : null
    return {
      id: run.id,
      domain: run.workspace_name,
      status,
      period: periodLabel(run, t, lang),
      generated: completed ? day : null,
      stamp,
      startedClock: run.started_at ? formatClock(run.started_at, lang) : null,
      failedDay: status === 'failed' ? day : null,
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
  // Every run in flight, not the rows: one may sit below the fifth briefing.
  // Trimmed to what the form's admission rule reads (it is a client island).
  const flying: InFlightRun[] = inFlight.map((run) => ({
    id: run.id,
    workspace_id: run.workspace_id,
    workspace_name: run.workspace_name,
    status: run.status,
    period_start: run.period_start,
    period_end: run.period_end,
    lookback_days: run.lookback_days,
  }))

  return (
    <HomeGrid
      ledger={
        <>
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
              <Ledger rows={rows} inFlight={flying} />
            )}
          </div>
        </>
      }
      card={<RunCard domains={domains} inFlight={flying} today={today} />}
    >
      <LiveRefresh processingIds={inFlight.map((run) => run.id)} />
    </HomeGrid>
  )
}

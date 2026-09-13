import { Card, StatBand } from '@/components/scanner-ui'
import { forPage } from '@/lib/bff/core/page'
import { runs as runsService } from '@/lib/bff/pipeline-runs/service'
import { fmt, formatNumber, formatPercent, type Lang, type T } from '@/lib/i18n'
import { getWorkspacesState } from '@/lib/workspace-server'
import { LiveRefresh } from '../dashboard/live-refresh'
import { inFlightIds } from '../dashboard/recent'
import { formatUsd } from './run-presentation'
import { matches, RunTabs, type Tab } from './run-tabs'
import { RunsTable } from './runs-table'
import { stoppableWorkspaces } from './stoppable'

/**
 * The runs page's streamed body: band, filter strip and table all read the one
 * list — every run across the user's domains — so they are one Suspense
 * boundary; they cannot arrive separately. Returns a single root so the page
 * can wrap it in a <ViewTransition> with its skeleton.
 */
export async function RunsSection({ tab, t, lang }: { tab: Tab; t: T; lang: Lang }) {
  // The service lists by the run clock (completion first); this table's
  // leading column is Started, so it reads in start order, newest first. The
  // live refresh below watches the run-clock order — the order the poll
  // shares — so the two in-flight sets can only differ when a run changed.
  // The page already awaited the workspaces (React-cached): the roles gate
  // which rows offer Stop.
  const [ledger, workspaces] = await Promise.all([
    forPage(runsService.listEverywhere()),
    getWorkspacesState(),
  ])
  const stoppable = stoppableWorkspaces(workspaces)
  const all = ledger
    .slice()
    .sort((a, b) => (b.started_at ?? b.run_date).localeCompare(a.started_at ?? a.run_date))
  const shown = all.filter((run) => matches(run, tab))

  const fetched = all.reduce((sum, run) => sum + run.total_papers_fetched, 0)
  const passed = all.reduce((sum, run) => sum + run.total_papers_passed_screening, 0)
  const spend = all.reduce((sum, run) => sum + run.usd_cost, 0)

  return (
    <div className="space-y-8">
      <StatBand
        items={[
          { label: t('Runs'), value: formatNumber(all.length, lang) },
          { label: t('Papers fetched'), value: formatNumber(fetched, lang) },
          {
            label: t('Passed screening'),
            value: formatNumber(passed, lang),
            sub:
              fetched > 0
                ? fmt(t('{share} of {n} fetched'), {
                    share: formatPercent((passed / fetched) * 100, lang),
                    n: formatNumber(fetched, lang),
                  })
                : undefined,
          },
          { label: t('Total spend'), value: formatUsd(spend, lang) },
        ]}
      />

      <RunTabs tab={tab} runs={all} t={t} lang={lang} />

      {shown.length === 0 ? (
        <Card>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {/* Status-neutral: the old line interpolated the raw `?status=`
                enum into an English sentence, which no dictionary can carry.
                The filter is already named in the strip above. */}
            {all.length === 0
              ? t('No pipeline runs yet.')
              : fmt(
                  all.length === 1
                    ? t('No runs match this filter. {n} run in total.')
                    : t('No runs match this filter. {n} runs in total.'),
                  { n: formatNumber(all.length, lang) },
                )}
          </p>
        </Card>
      ) : (
        <RunsTable runs={shown} stoppable={stoppable} t={t} lang={lang} />
      )}

      {/* A run ending or stopping re-reads the page: its Stop goes, its row settles. */}
      <LiveRefresh processingIds={inFlightIds(ledger)} />
    </div>
  )
}

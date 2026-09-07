import { Card, StatBand } from '@/components/scanner-ui'
import { forPage } from '@/lib/bff/core/page'
import { runs as runsService } from '@/lib/bff/pipeline-runs/service'
import { formatUsd } from './run-presentation'
import { matches, RunTabs, type Tab } from './run-tabs'
import { RunsTable } from './runs-table'

/**
 * The runs page's streamed body: band, filter strip and table all read the one
 * list — every run across the user's domains — so they are one Suspense
 * boundary; they cannot arrive separately. Returns a single root so the page
 * can wrap it in a <ViewTransition> with its skeleton.
 */
export async function RunsSection({ tab }: { tab: Tab }) {
  const all = await forPage(runsService.listEverywhere())
  const shown = all.filter((run) => matches(run, tab))

  const fetched = all.reduce((sum, run) => sum + run.total_papers_fetched, 0)
  const passed = all.reduce((sum, run) => sum + run.total_papers_passed_screening, 0)
  const spend = all.reduce((sum, run) => sum + run.usd_cost, 0)

  return (
    <div className="space-y-8">
      <StatBand
        items={[
          { label: 'Runs', value: all.length },
          { label: 'Papers fetched', value: fetched.toLocaleString('en-US') },
          {
            label: 'Passed screening',
            value: passed.toLocaleString('en-US'),
            sub:
              fetched > 0
                ? `${Math.round((passed / fetched) * 100)}% of ${fetched.toLocaleString('en-US')} fetched`
                : undefined,
          },
          { label: 'Total spend', value: formatUsd(spend) },
        ]}
      />

      <RunTabs tab={tab} runs={all} />

      {shown.length === 0 ? (
        <Card>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {all.length === 0
              ? 'No pipeline runs yet.'
              : `No ${tab} runs. ${all.length} run${all.length === 1 ? '' : 's'} in total.`}
          </p>
        </Card>
      ) : (
        <RunsTable runs={shown} />
      )}
    </div>
  )
}

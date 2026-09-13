import { Card, PageHeader, SectionLabel, StatBand } from '@/components/scanner-ui'
import { componentRuns as componentRunsService } from '@/lib/bff/component-runs/service'
import { forPage } from '@/lib/bff/core/page'
import { ProblemError } from '@/lib/bff/core/problem'
import { runs as runsService } from '@/lib/bff/pipeline-runs/service'
import { fmt, formatNumber, formatPercent, type Lang, type T } from '@/lib/i18n'
import { notFound } from 'next/navigation'
import { LiveRefresh } from '../../dashboard/live-refresh'
import { inFlightIds } from '../../dashboard/recent'
import { formatUsd, offersStop, RunStatus, shortId } from '../run-presentation'
import { StopRunButton } from '../stop-run-button'
import { RunFacts } from './run-facts'
import { StepTimeline } from './step-timeline'

/**
 * The run page's streamed sections: one async Server Component per Suspense
 * boundary, each awaiting only its own data. Both services are React-cached,
 * so the run the head fetches is the same promise the steps section reads for
 * the spend line — one upstream call each.
 *
 * `forPage` sends an expired session through the logout flow; the 404 catch
 * turns an unknown (or non-member) run id into the segment's not-found page.
 * The status code is 200 once streaming has begun (the shell went out with
 * loading.tsx); the page is behind auth, so nothing indexes it either way.
 */
function getRun(id: string) {
  return runsService.get(id).catch((error: unknown) => {
    if (error instanceof ProblemError && error.problem.status === 404) notFound()
    throw error
  })
}

function getSteps(id: string) {
  return componentRunsService.listAll(id).catch((error: unknown) => {
    if (error instanceof ProblemError && error.problem.status === 404) return []
    throw error
  })
}

/** Header, funnel band and the facts card — everything the run record alone gives. */
export async function RunHead({ id, t, lang }: { id: string; t: T; lang: Lang }) {
  const run = await forPage(getRun(id))
  // Only a run in flight can change under the reader. The poller compares
  // in-flight sets drawn from the same window on both sides (dashboard/recent.ts),
  // so it watches the list, never `[run.id]`; one extra call, only while live.
  const watched = offersStop(run.status)
    ? inFlightIds(await forPage(runsService.listEverywhere()))
    : null

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={run.workspace_name}
        title={fmt(t('Run {id}'), { id: shortId(run.id) })}
        description={run.status_message ?? undefined}
        actions={
          <>
            <RunStatus run={run} t={t} />
            <StopRunButton run={run} />
          </>
        }
      />
      {watched && <LiveRefresh processingIds={watched} />}

      <StatBand
        flow
        items={[
          {
            label: t('Fetched'),
            value: formatNumber(run.total_papers_fetched, lang),
            sub: t('from the sources'),
          },
          {
            label: t('Passed screening'),
            value: formatNumber(run.total_papers_passed_screening, lang),
            sub:
              run.total_papers_fetched > 0
                ? fmt(t('{share} of fetched'), {
                    share: formatPercent(
                      (run.total_papers_passed_screening / run.total_papers_fetched) * 100,
                      lang,
                    ),
                  })
                : undefined,
          },
          {
            label: t('Papers stored'),
            value: formatNumber(run.papers_count, lang),
            sub: t('rows in this run'),
          },
          {
            label: t('Extractions'),
            value: formatNumber(run.extractions_count, lang),
            sub: t('parameter values'),
          },
        ]}
      />

      <Card>
        <RunFacts run={run} t={t} lang={lang} />
      </Card>
    </div>
  )
}

/** The failed-steps notice and the timeline — everything that needs the step list. */
export async function Steps({ id, t, lang }: { id: string; t: T; lang: Lang }) {
  const [run, steps] = await forPage(Promise.all([getRun(id), getSteps(id)]))

  const failedSteps = steps.filter((step) => step.status === 'failed' || step.status === 'aborted')

  // Only steps that recorded spend contribute; the rest are genuinely unmeasured.
  const stepSpend = steps.reduce((sum, step) => sum + (step.cost.usd ?? 0), 0)
  const unattributed = run.usd_cost - stepSpend

  return (
    <div className="space-y-8">
      {failedSteps.length > 0 && (
        <div className="rounded-sm border border-red-300/60 bg-red-50 p-4 dark:border-red-400/25 dark:bg-red-500/10">
          <p className="text-sm font-medium text-red-900 dark:text-red-200">
            {fmt(
              failedSteps.length === 1
                ? t('{n} step did not succeed: {steps}.')
                : t('{n} steps did not succeed: {steps}.'),
              {
                n: formatNumber(failedSteps.length, lang),
                // Step titles are frontend copy (component-runs/normalise.ts),
                // so the list reads in the UI language, like the timeline.
                steps: failedSteps.map((step) => t(step.label)).join(', '),
              },
            )}
          </p>
        </div>
      )}

      <section className="space-y-4">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <SectionLabel>{t('Steps')}</SectionLabel>
          {steps.length > 0 && (
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              {fmt(steps.length === 1 ? t('{n} step') : t('{n} steps'), {
                n: formatNumber(steps.length, lang),
              })}
              {' · '}
              {fmt(t('{usd} attributed'), { usd: formatUsd(stepSpend, lang) })}
              {/* A gap here means spend the engine booked on the run but not on
                  any step — worth seeing rather than silently absorbing. */}
              {Math.abs(unattributed) >= 0.0001 && (
                <span className="text-amber-700 dark:text-amber-400">
                  {' · '}
                  {fmt(t('{usd} unattributed'), { usd: formatUsd(unattributed, lang) })}
                </span>
              )}
            </p>
          )}
        </div>

        {steps.length === 0 ? (
          <Card>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              {t('No steps recorded for this run.')}
            </p>
          </Card>
        ) : (
          <Card className="py-1">
            <StepTimeline steps={steps} t={t} lang={lang} />
          </Card>
        )}
      </section>
    </div>
  )
}

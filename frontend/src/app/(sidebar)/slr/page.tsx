import { slr } from '@/lib/bff/slr/service'
import { SlrConsoleClient } from './slr-console-client'

export const dynamic = 'force-dynamic'

interface SlrPageProps {
  searchParams?: Promise<{ runId?: string }>
}

export default async function SlrConsolePage({ searchParams }: SlrPageProps) {
  const sp = searchParams ? await searchParams : {}
  const runs = await slr.getRuns()

  const defaultRunId = sp.runId || (runs.length > 0 ? runs[0].id : null)

  const [metrics, robAssessments, disputes] = await Promise.all([
    defaultRunId ? slr.getMetrics(defaultRunId).catch(() => null) : Promise.resolve(null),
    defaultRunId ? slr.getRiskOfBias(defaultRunId).catch(() => []) : Promise.resolve([]),
    slr.getDisputes('all').catch(() => []),
  ])

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <SlrConsoleClient
        initialRuns={runs}
        initialMetrics={metrics}
        initialRob={robAssessments}
        initialDisputes={disputes}
        initialRunId={defaultRunId}
      />
    </div>
  )
}

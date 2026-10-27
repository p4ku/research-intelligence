import { slr } from '@/lib/bff/slr/service'
import type { Metadata } from 'next'
import { SLRStudiesClient } from './studies-client'

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Included Studies · PRISMA 2020 SLR',
  description: 'Catalogue of empirical studies admitted to qualitative synthesis and meta-analysis.',
}

interface SLRStudiesPageProps {
  searchParams?: Promise<{ runId?: string }>
}

export default async function SLRStudiesPage({ searchParams }: SLRStudiesPageProps) {
  const sp = searchParams ? await searchParams : {}
  const runs = await slr.getRuns()

  const defaultRunId = sp.runId || (runs.length > 0 ? runs[0].id : null)

  const [metrics, robAssessments] = await Promise.all([
    defaultRunId ? slr.getMetrics(defaultRunId).catch(() => null) : Promise.resolve(null),
    defaultRunId ? slr.getRiskOfBias(defaultRunId).catch(() => []) : Promise.resolve([]),
  ])

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <SLRStudiesClient
        initialRuns={runs}
        initialMetrics={metrics}
        initialRob={robAssessments}
        initialRunId={defaultRunId}
      />
    </div>
  )
}

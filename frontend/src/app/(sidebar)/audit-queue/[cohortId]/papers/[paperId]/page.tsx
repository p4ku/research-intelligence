import { audit } from '@/lib/bff/audit/service'
import { notFound } from 'next/navigation'
import { WorkspaceClient } from './workspace-client'

export const dynamic = 'force-dynamic'

export default async function PaperReviewPage({
  params,
}: {
  params: Promise<{ cohortId: string; paperId: string }>
}) {
  const { cohortId, paperId } = await params

  let paper
  let cohort
  try {
    const res = await Promise.all([audit.getPaper(cohortId, paperId), audit.getCohort(cohortId)])
    paper = res[0]
    cohort = res[1]
  } catch (err) {
    console.error('[audit-queue] failed to load paper audit workspace', err)
    notFound()
  }

  if (!paper) {
    notFound()
  }

  return <WorkspaceClient cohortId={cohortId} paper={paper} cohort={cohort} />
}

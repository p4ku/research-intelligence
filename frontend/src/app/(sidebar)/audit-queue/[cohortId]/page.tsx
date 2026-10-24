import { audit } from '@/lib/bff/audit/service'
import { notFound, redirect } from 'next/navigation'

export const dynamic = 'force-dynamic'

export default async function CohortRedirectPage({
  params,
}: {
  params: Promise<{ cohortId: string }>
}) {
  const { cohortId } = await params
  const cohort = await audit.getCohort(cohortId)

  if (!cohort || !cohort.papers || cohort.papers.length === 0) {
    notFound()
  }

  const targetPaperId =
    cohort.first_unreviewed_paper_id || cohort.papers[0]?.paper_id

  if (!targetPaperId) {
    notFound()
  }

  redirect(`/audit-queue/${cohortId}/papers/${targetPaperId}`)
}

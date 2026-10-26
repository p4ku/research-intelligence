'use client'

import type { AuditCohortDetail, AuditPaperDetail, AuditReviewResult } from '@/lib/bff/audit/schema'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { AuditDecisionPane } from './audit-decision-pane'
import { CompletionModal } from './completion-modal'
import { PdfViewerPane } from './pdf-viewer-pane'
import { ReviewHeader } from './review-header'

export interface ActiveEvidence {
  quote: string
  page_number?: number | null
  section?: string | null
}

interface WorkspaceClientProps {
  cohortId: string
  paper: AuditPaperDetail
  cohort: AuditCohortDetail
}

export function WorkspaceClient({ cohortId, paper, cohort }: WorkspaceClientProps) {
  const router = useRouter()
  const [showCompletionModal, setShowCompletionModal] = useState<boolean>(false)

  // Initialize activeEvidence with first evidence quote or extraction quote if available
  const initialEvidence: ActiveEvidence | null =
    paper.evidence_quotes && paper.evidence_quotes.length > 0
      ? {
          quote: paper.evidence_quotes[0].quote,
          page_number: paper.evidence_quotes[0].page_number,
          section: paper.evidence_quotes[0].section,
        }
      : paper.extractions && paper.extractions.length > 0 && paper.extractions[0].text_evidence
        ? {
            quote: paper.extractions[0].text_evidence,
            page_number: paper.extractions[0].page_number,
          }
        : null

  const [activeEvidence, setActiveEvidence] = useState<ActiveEvidence | null>(initialEvidence)

  // Prefetch adjacent paper routes to ensure zero-latency transitions
  useEffect(() => {
    if (paper.next_paper_id) {
      router.prefetch(`/audit-queue/${cohortId}/papers/${paper.next_paper_id}`)
    }
    if (paper.prev_paper_id) {
      router.prefetch(`/audit-queue/${cohortId}/papers/${paper.prev_paper_id}`)
    }
  }, [cohortId, paper.next_paper_id, paper.prev_paper_id, router])

  // Arrow key navigation (← for Prev, → for Next) when not typing in an input
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement
      const isInput =
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.tagName === 'SELECT' ||
          target.isContentEditable)

      if (isInput) return

      if (e.key === 'ArrowLeft' && paper.prev_paper_id) {
        e.preventDefault()
        router.push(`/audit-queue/${cohortId}/papers/${paper.prev_paper_id}`)
      } else if (e.key === 'ArrowRight' && paper.next_paper_id) {
        e.preventDefault()
        router.push(`/audit-queue/${cohortId}/papers/${paper.next_paper_id}`)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [cohortId, paper.prev_paper_id, paper.next_paper_id, router])

  function handleSubmitted(result: AuditReviewResult) {
    if (result.is_cohort_complete) {
      setShowCompletionModal(true)
      return
    }

    if (result.next_unreviewed_paper_id) {
      router.push(`/audit-queue/${cohortId}/papers/${result.next_unreviewed_paper_id}`)
      router.refresh()
    } else if (paper.next_paper_id) {
      router.push(`/audit-queue/${cohortId}/papers/${paper.next_paper_id}`)
      router.refresh()
    } else {
      router.push('/audit-queue')
      router.refresh()
    }
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col overflow-hidden bg-zinc-50 dark:bg-zinc-950">
      <ReviewHeader
        cohortId={cohortId}
        currentIndex={paper.current_index}
        totalCount={paper.total_count}
        prevPaperId={paper.prev_paper_id}
        nextPaperId={paper.next_paper_id}
        cohort={cohort}
      />

      <div className="grid flex-1 grid-cols-1 overflow-hidden lg:grid-cols-12">
        {/* Left Pane: PDF / Document Viewer (7 cols = ~58%) */}
        <div className="h-full overflow-hidden border-r border-zinc-200 lg:col-span-7 dark:border-zinc-800">
          <PdfViewerPane
            paper={paper}
            activeEvidence={activeEvidence}
            onSelectEvidence={setActiveEvidence}
            onClearEvidence={() => setActiveEvidence(null)}
          />
        </div>

        {/* Right Pane: AI Screening Audit & Actions (5 cols = ~42%) */}
        <div className="h-full overflow-hidden lg:col-span-5">
          <AuditDecisionPane
            cohortId={cohortId}
            paper={paper}
            onSubmitted={handleSubmitted}
            isExtractionStage={cohort.stage === 'parameter_extraction'}
            activeEvidence={activeEvidence}
            onSelectEvidence={setActiveEvidence}
          />
        </div>
      </div>

      <CompletionModal
        isOpen={showCompletionModal}
        pipelineRunId={cohort.pipeline_run_id}
        cohortId={cohortId}
      />

      {/* Prefetch next paper PDF binary for 0ms transition */}
      {paper.next_paper_id && (
        <link
          rel="prefetch"
          href={`/bff/papers/${paper.next_paper_id}/pdf`}
          as="fetch"
          crossOrigin="anonymous"
        />
      )}
    </div>
  )
}

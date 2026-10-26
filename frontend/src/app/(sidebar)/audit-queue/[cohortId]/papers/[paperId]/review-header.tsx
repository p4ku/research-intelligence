'use client'

import { Button } from '@/components/button'
import { Link } from '@/components/link'
import type { AuditCohortDetail } from '@/lib/bff/audit/schema'
import clsx from 'clsx'

interface ReviewHeaderProps {
  cohortId: string
  currentIndex: number
  totalCount: number
  prevPaperId: string | null
  nextPaperId: string | null
  cohort?: AuditCohortDetail | null
}

function gateBadgeLabel(stage?: string | null): string {
  switch (stage) {
    case 'abstract_screening':
      return 'Gate 1: Abstract'
    case 'full_text_screening':
      return 'Gate 2: Full-Text'
    case 'parameter_extraction':
      return 'Gate 3: Extraction'
    default:
      return 'Checkpoint Audit'
  }
}

export function ReviewHeader({
  cohortId,
  currentIndex,
  totalCount,
  prevPaperId,
  nextPaperId,
  cohort,
}: ReviewHeaderProps) {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-zinc-200 bg-white px-4 dark:border-zinc-800 dark:bg-zinc-900">
      {/* Left: Back & Breadcrumb */}
      <div className="flex items-center gap-3">
        <Button href="/audit-queue" plain className="text-xs font-semibold">
          ← Queue
        </Button>
        <span className="text-zinc-300 dark:text-zinc-700">|</span>
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-zinc-900 dark:text-white">
            HITL Systematic Review Audit
          </span>
          <span className="rounded-full bg-blue-500/10 px-2 py-0.5 text-[10px] font-medium text-blue-600 dark:bg-blue-400/10 dark:text-blue-300">
            {gateBadgeLabel(cohort?.stage)}
          </span>
        </div>
      </div>

      {/* Middle: Progress dots */}
      <div className="hidden items-center gap-2 md:flex">
        <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
          Progress: <strong className="text-zinc-900 dark:text-white">{currentIndex}</strong> of{' '}
          {totalCount}
        </span>
        {cohort?.papers && (
          <div className="flex items-center gap-1">
            {cohort.papers.map((p, idx) => {
              const isCurrent = idx + 1 === currentIndex
              const isDone = p.is_reviewed
              return (
                <Link
                  key={p.paper_id}
                  href={`/audit-queue/${cohortId}/papers/${p.paper_id}`}
                  title={`Paper ${idx + 1}: ${p.title}`}
                  className={clsx(
                    'size-2.5 rounded-full transition-all',
                    isCurrent
                      ? 'ring-2 ring-blue-500 ring-offset-1 dark:ring-offset-zinc-900'
                      : '',
                    isDone
                      ? 'bg-emerald-500 hover:bg-emerald-600'
                      : 'bg-zinc-300 hover:bg-zinc-400 dark:bg-zinc-700 dark:hover:bg-zinc-600',
                  )}
                />
              )
            })}
          </div>
        )}
      </div>

      {/* Right: Traversal buttons */}
      <div className="flex items-center gap-2">
        <Button
          href={prevPaperId ? `/audit-queue/${cohortId}/papers/${prevPaperId}` : undefined}
          disabled={!prevPaperId}
          plain
          className="text-xs font-semibold"
          title="Previous Paper"
        >
          ← Prev
        </Button>
        <Button
          href={nextPaperId ? `/audit-queue/${cohortId}/papers/${nextPaperId}` : undefined}
          disabled={!nextPaperId}
          plain
          className="text-xs font-semibold"
          title="Next Paper"
        >
          Next →
        </Button>
      </div>
    </header>
  )
}

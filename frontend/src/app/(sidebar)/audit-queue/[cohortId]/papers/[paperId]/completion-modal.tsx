'use client'

import { Button } from '@/components/button'

interface CompletionModalProps {
  isOpen: boolean
  pipelineRunId?: string
  cohortId: string
  onClose?: () => void
}

export function CompletionModal({
  isOpen,
  pipelineRunId,
  cohortId: _cohortId,
}: CompletionModalProps) {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-xs">
      <div className="w-full max-w-md rounded-2xl border border-zinc-200 bg-white p-6 shadow-2xl dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex flex-col items-center text-center">
          <div className="flex size-14 items-center justify-center rounded-full bg-emerald-100 text-2xl text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-400">
            ✓
          </div>
          <h2 className="mt-4 text-lg font-bold text-zinc-900 dark:text-white">
            Audit Checkpoint Complete!
          </h2>
          <p className="mt-2 text-xs leading-relaxed text-zinc-600 dark:text-zinc-400">
            All sampled articles in this checkpoint cohort have been independently evaluated. The
            consensus gate has been unlocked and the pipeline has automatically resumed downstream
            processing.
          </p>
        </div>

        <div className="mt-6 flex flex-col gap-2">
          {pipelineRunId && (
            <Button
              href={`/runs/${pipelineRunId}`}
              color="dark/zinc"
              className="w-full justify-center text-xs font-semibold"
            >
              Monitor Pipeline Run →
            </Button>
          )}
          <Button href="/audit-queue" plain className="w-full justify-center text-xs">
            Return to Audit Queue
          </Button>
        </div>
      </div>
    </div>
  )
}

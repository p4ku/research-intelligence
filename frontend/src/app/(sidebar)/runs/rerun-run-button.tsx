'use client'

import { ErrorNote } from '@/components/scanner-ui'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Spinner } from '@/components/ui/spinner'
import { BffClientError, bffFetch } from '@/lib/bff/client'
import type { PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import { errorsFromSubmit } from '@/lib/bff/problem-copy'
import { fmt } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import { ArrowPathIcon } from '@heroicons/react/16/solid'
import { useRouter } from 'next/navigation'
import { useRef, useState, useTransition } from 'react'

export type RerunRun = Pick<PipelineRun, 'id' | 'workspace_name' | 'status'>

export function RerunRunButton({ run }: { run: RerunRun }) {
  const t = useT()
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [rerunning, setRerunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [, startTransition] = useTransition()
  const triggerRef = useRef<HTMLButtonElement | null>(null)

  async function confirm() {
    if (rerunning) return
    setRerunning(true)
    setError(null)
    try {
      await bffFetch<{ pipeline_run_id: string }>(`/bff/pipeline-runs/${run.id}/rerun`, {
        method: 'POST',
      })
      setOpen(false)
      startTransition(() => router.refresh())
    } catch (err) {
      console.error('[runs] rerun failed', err)
      if (err instanceof BffClientError && err.problem.type === '/problems/forbidden') {
        setError(t('Only an admin of this domain can rerun its runs.'))
      } else {
        setError(errorsFromSubmit(err, [], t, t("Couldn't rerun this run. Try again."))._)
      }
    } finally {
      setRerunning(false)
    }
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => {
          setError(null)
          setOpen(true)
        }}
        className="relative inline-flex items-center gap-1 rounded-sm border border-line px-2 py-0.5 text-xs font-medium text-zinc-700 transition-colors hover:border-zinc-400 hover:text-zinc-950 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 dark:text-zinc-200 dark:hover:text-white"
      >
        <ArrowPathIcon className="size-3" aria-hidden="true" />
        {t('Rerun')}
      </button>

      <AlertDialog
        open={open}
        onOpenChange={(next) => {
          if (!next && !rerunning) setOpen(false)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('Rerun this pipeline?')}</AlertDialogTitle>
            <AlertDialogDescription>
              {fmt(
                t('The {domain} pipeline run will re-execute from the failed step or beginning.'),
                { domain: run.workspace_name },
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {error && <ErrorNote>{error}</ErrorNote>}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={rerunning}>{t('Cancel')}</AlertDialogCancel>
            <AlertDialogAction
              disabled={rerunning}
              onClick={(event) => {
                event.preventDefault()
                void confirm()
              }}
            >
              {rerunning && <Spinner className="size-3.5" aria-hidden="true" />}
              {rerunning ? t('Rerunning…') : t('Rerun')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

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
import type { AbortedRun, PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import { errorsFromSubmit } from '@/lib/bff/problem-copy'
import { fmt, type T } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import { StopIcon } from '@heroicons/react/16/solid'
import { useRouter } from 'next/navigation'
import { useRef, useState, useTransition, type RefObject } from 'react'
import { offersStop } from './run-presentation'

export type StopRun = Pick<PipelineRun, 'id' | 'workspace_name' | 'status'>

/**
 * Stop for one run in flight: the button nominates, the AlertDialog confirms,
 * and the page re-reads itself so the row settles to Aborted. A failure keeps
 * the dialog open with the reason — a paid run is never stopped silently, and
 * never fails to stop silently either.
 *
 * Mounted on every row (the rows are server-rendered, so this is the only
 * place that can remember an open dialog across a refresh), but nothing
 * renders for a run that has ended unless its dialog is open: then the
 * dialog stays, its Stop disabled, so a reader whose run ended under them —
 * by itself, or a 409 from a stale click — sees why, on the row that now
 * reads Completed or Aborted behind it. The page re-reads when they dismiss,
 * not before: a refresh with the dialog open would drop the row from a
 * filtered tab and the dialog with it. A closed Radix root renders no DOM.
 *
 * Only rendered for runs the reader may stop (the sections check the
 * workspace role); the 403 copy below still covers a role that changed
 * under a stale page.
 */
export function StopRunButton({ run }: { run: StopRun }) {
  const [open, setOpen] = useState(false)
  const live = offersStop(run.status)
  if (!live && !open) return null
  return <StopRunControl run={run} live={live} open={open} setOpen={setOpen} />
}

function StopRunControl({
  run,
  live,
  open,
  setOpen,
}: {
  run: StopRun
  live: boolean
  open: boolean
  setOpen: (open: boolean) => void
}) {
  const t = useT()
  const router = useRouter()
  const [stopping, setStopping] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // A 409 says the run ended before the click landed. The row behind still
  // reads Running until the page re-reads on dismiss (the poller holds off
  // under a modal), so the dialog stops offering Stop on its own.
  const [ended, setEnded] = useState(false)
  const [, startTransition] = useTransition()
  const triggerRef = useRef<HTMLButtonElement | null>(null)
  const settledRef = useRef<HTMLSpanElement | null>(null)

  async function confirm() {
    if (stopping) return
    setStopping(true)
    setError(null)
    try {
      await bffFetch<AbortedRun>(`/bff/pipeline-runs/${run.id}/abort`, { method: 'POST' })
      setOpen(false)
      // Django has written `aborted` before it answers: re-read for the row.
      startTransition(() => router.refresh())
    } catch (err) {
      console.error('[runs] stop failed', err)
      setError(stopErrorMessage(err, t))
      if (problemType(err) === '/problems/conflict') setEnded(true)
    } finally {
      setStopping(false)
    }
  }

  return (
    <StopRunView
      run={run}
      t={t}
      live={live && !ended}
      open={open}
      stopping={stopping}
      error={error}
      triggerRef={triggerRef}
      settledRef={settledRef}
      onOpen={() => {
        setError(null)
        setOpen(true)
      }}
      onClose={() => {
        if (stopping) return
        setOpen(false)
        // A refusal (the run ended first, or a role that changed) means the
        // page is stale: re-read it now that the reader has seen why.
        const stale = error !== null || ended || !live
        setError(null)
        setEnded(false)
        if (stale) startTransition(() => router.refresh())
      }}
      onConfirm={() => void confirm()}
    />
  )
}

const problemType = (error: unknown): string | null =>
  error instanceof BffClientError ? error.problem.type : null

/**
 * The sentence for a failed stop. The two refusals the backend names get
 * action-specific copy: the house conflict line says "reload the page", but
 * this control reloads for the reader; the house forbidden line does not say
 * what would be allowed.
 */
export function stopErrorMessage(error: unknown, t: T): string {
  switch (problemType(error)) {
    case '/problems/conflict':
      return t('This run has already ended.')
    case '/problems/forbidden':
      return t('Only an admin or manager of this domain can stop its runs.')
    default:
      return errorsFromSubmit(error, [], t, t("Couldn't stop this run. Try again."))._
  }
}

/** The markup, hook-free, so it renders under bun test without the app router. */
export function StopRunView({
  run,
  t,
  live,
  open,
  stopping,
  error,
  triggerRef,
  settledRef,
  onOpen,
  onClose,
  onConfirm,
}: {
  run: Pick<StopRun, 'workspace_name'>
  t: T
  /** Still in flight — the trigger shows and the dialog's Stop is enabled. */
  live: boolean
  open: boolean
  stopping: boolean
  error: string | null
  triggerRef?: RefObject<HTMLButtonElement | null>
  /** Where focus lands on close once the trigger is gone: the row, not <body>. */
  settledRef?: RefObject<HTMLSpanElement | null>
  onOpen: () => void
  onClose: () => void
  onConfirm: () => void
}) {
  return (
    <>
      {/* Positioned, like Home's Retry, so it paints above a linked row's
          overlay and takes the click; the link is a sibling, not an ancestor. */}
      {live ? (
        <button
          ref={triggerRef}
          type="button"
          onClick={onOpen}
          className="relative inline-flex items-center gap-1 rounded-sm border border-line px-2 py-0.5 text-xs font-medium text-zinc-700 transition-colors hover:border-zinc-400 hover:text-zinc-950 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 dark:text-zinc-200 dark:hover:text-white"
        >
          <StopIcon className="size-3" aria-hidden="true" />
          {t('Stop')}
        </button>
      ) : (
        <span ref={settledRef} tabIndex={-1} className="sr-only" />
      )}

      <AlertDialog
        open={open}
        onOpenChange={(next) => {
          if (!next) onClose()
        }}
      >
        <AlertDialogContent
          onCloseAutoFocus={(event) => {
            const target = triggerRef?.current ?? settledRef?.current
            if (!target) return
            event.preventDefault()
            target.focus()
          }}
        >
          <AlertDialogHeader>
            <AlertDialogTitle>{t('Stop this run?')}</AlertDialogTitle>
            <AlertDialogDescription>
              {/* Django marks the run aborted and dispatches no further step; the
                  step already executing runs to its end. Say that, not "at once". */}
              {fmt(
                t(
                  'The {domain} run will stop once its current step finishes. This cannot be undone.',
                ),
                { domain: run.workspace_name },
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {error && <ErrorNote>{error}</ErrorNote>}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={stopping}>{t('Cancel')}</AlertDialogCancel>
            <AlertDialogAction
              disabled={stopping || !live}
              onClick={(event) => {
                // Radix closes on Action by default; close only on success.
                event.preventDefault()
                onConfirm()
              }}
            >
              {stopping && <Spinner className="size-3.5" aria-hidden="true" />}
              {stopping ? t('Stopping…') : t('Stop')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

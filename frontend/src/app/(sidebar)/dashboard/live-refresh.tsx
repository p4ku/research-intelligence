'use client'

import { bffFetch } from '@/lib/bff/client'
import type { Page } from '@/lib/bff/core/pagination'
import type { PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import { useRouter } from 'next/navigation'
import { useEffect, useRef } from 'react'
import { inFlightIds, POLL_RUNS } from './recent'

const BUSY_MS = 10_000
const IDLE_MS = 60_000

/**
 * Keeps Home current without a reload — the spec's "Home updates
 * automatically" — and the form's note about what is in flight. It polls
 * the runs list (one small Django call) every 10 s while a run is in flight
 * and every 60 s otherwise, and re-reads the page only when the set of
 * in-flight runs differs from what this render was built from: a run
 * finishing, or another analyst starting one. Both sets are drawn from the
 * same POLL_RUNS newest runs (recent.ts), so they differ only when a run
 * really changed. `router.refresh()` keeps client state (an open row, the
 * form), so nothing jumps. Nothing polls while the tab is hidden or while a
 * confirmation dialog is open; a tab coming back checks at once. Also mounted
 * on /runs and, while a run is live, on /runs/[id].
 */
export function LiveRefresh({
  processingIds,
}: {
  /** `inFlightIds` of the render's runs. */
  processingIds: string[]
}) {
  const router = useRouter()
  const known = [...processingIds].sort().join(',')
  const refreshing = useRef(false)

  useEffect(() => {
    let cancelled = false
    async function check() {
      if (document.visibilityState !== 'visible' || refreshing.current) return
      // Never re-read the page from under a modal: a refresh can drop the row
      // a confirmation belongs to (a filtered tab, a run that just ended) and
      // the dialog with it. The dialog re-reads the page when it closes.
      if (document.querySelector('[role="alertdialog"]')) return
      try {
        const page = await bffFetch<Page<PipelineRun>>(`/bff/pipeline-runs?page_size=${POLL_RUNS}`)
        if (!cancelled && inFlightIds(page.results).join(',') !== known) {
          refreshing.current = true
          router.refresh()
        }
      } catch {
        // A failed poll is not an error the reader needs: the next tick retries.
      }
    }
    const id = window.setInterval(check, known ? BUSY_MS : IDLE_MS)
    document.addEventListener('visibilitychange', check)
    return () => {
      cancelled = true
      window.clearInterval(id)
      document.removeEventListener('visibilitychange', check)
    }
  }, [known, router])

  // A new render (new `known`) means the refresh landed.
  useEffect(() => {
    refreshing.current = false
  }, [known])

  return null
}

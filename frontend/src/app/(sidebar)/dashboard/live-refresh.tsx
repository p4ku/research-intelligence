'use client'

import { bffFetch } from '@/lib/bff/client'
import type { Page } from '@/lib/bff/core/pagination'
import type { PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import { useRouter } from 'next/navigation'
import { useEffect, useRef } from 'react'

/** How many runs the poll reads — the same five the ledger shows. */
const RECENT = 5
const BUSY_MS = 10_000
const IDLE_MS = 60_000

const inFlight = (page: Page<PipelineRun>) =>
  page.results
    .filter((run) => run.status === 'running' || run.status === 'pending')
    .map((run) => run.id)
    .sort()
    .join(',')

/**
 * Keeps Home current without a reload — the spec's "Home updates
 * automatically" and "disable new runs globally while processing". It polls
 * the runs list (one small Django call) every 10 s while a run is in flight
 * and every 60 s otherwise, and re-reads the page only when the set of
 * in-flight runs differs from what this render was built from: a run
 * finishing, or another analyst starting one. `router.refresh()` keeps
 * client state (an open row, the form), so nothing jumps. Nothing polls
 * while the tab is hidden; a tab coming back checks at once.
 */
export function LiveRefresh({ processingIds }: { processingIds: string[] }) {
  const router = useRouter()
  const known = [...processingIds].sort().join(',')
  const refreshing = useRef(false)

  useEffect(() => {
    let cancelled = false
    async function check() {
      if (document.visibilityState !== 'visible' || refreshing.current) return
      try {
        const page = await bffFetch<Page<PipelineRun>>(`/bff/pipeline-runs?page_size=${RECENT}`)
        if (!cancelled && inFlight(page) !== known) {
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

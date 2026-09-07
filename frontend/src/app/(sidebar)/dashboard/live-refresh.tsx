'use client'

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

/**
 * While a run is processing, Home re-reads itself every few seconds so the
 * row turns into the new Current briefing without a reload — the spec's
 * "Home updates automatically". `router.refresh()` re-renders the server
 * tree and keeps client state (an open row, the form), so nothing jumps.
 * Nothing polls while no run is in flight, or while the tab is hidden; a
 * tab coming back refreshes once immediately.
 */
export function LiveRefresh({ active, everyMs = 10_000 }: { active: boolean; everyMs?: number }) {
  const router = useRouter()
  useEffect(() => {
    if (!active) return
    const tick = () => {
      if (document.visibilityState === 'visible') router.refresh()
    }
    const id = window.setInterval(tick, everyMs)
    document.addEventListener('visibilitychange', tick)
    return () => {
      window.clearInterval(id)
      document.removeEventListener('visibilitychange', tick)
    }
  }, [active, everyMs, router])
  return null
}

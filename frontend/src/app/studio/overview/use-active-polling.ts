'use client'

import { useEffect, useRef } from 'react'

/**
 * Re-run `onTick` every `intervalMs` while `active`, skipping ticks while
 * the tab is hidden or a tick is still in flight, and ticking at once when
 * the tab comes back. After a failed tick the interval doubles up to four
 * times the base; a successful tick restores it. `onTick` is read through a
 * ref so the timer never resubscribes on render.
 */
export function useActivePolling({
  active,
  intervalMs = 30_000,
  onTick,
}: {
  active: boolean
  intervalMs?: number
  /** Resolve true on success, false on a failure worth backing off from. */
  onTick: () => Promise<boolean>
}) {
  const tickRef = useRef(onTick)
  tickRef.current = onTick

  useEffect(() => {
    if (!active) return
    let timer: ReturnType<typeof setTimeout> | null = null
    let inFlight = false
    let delay = intervalMs
    let stopped = false

    const schedule = () => {
      if (stopped) return
      if (timer) clearTimeout(timer)
      timer = setTimeout(run, delay)
    }
    const run = async () => {
      if (stopped) return
      if (document.hidden || inFlight) {
        schedule()
        return
      }
      inFlight = true
      let ok = false
      try {
        ok = await tickRef.current()
      } catch {
        ok = false
      } finally {
        inFlight = false
      }
      delay = ok ? intervalMs : Math.min(delay * 2, intervalMs * 4)
      schedule()
    }
    const onVisible = () => {
      if (!document.hidden) void run()
    }

    document.addEventListener('visibilitychange', onVisible)
    schedule()
    return () => {
      stopped = true
      if (timer) clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [active, intervalMs])
}

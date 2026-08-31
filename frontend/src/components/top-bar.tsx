'use client'

import { useT } from '@/lib/i18n-client'
import { useEffect, useSyncExternalStore } from 'react'

/** One in-page section the top bar links to. The target element carries the id. */
export interface TopBarAnchor {
  id: string
  label: string
}

// Module-level store rather than context: publishing anchors must re-render
// only the top bar. A context provider around the layout would re-render the
// whole shell mid-hydration and desync Headless UI's generated ids.
const EMPTY: TopBarAnchor[] = []
let currentAnchors: TopBarAnchor[] = EMPTY
const listeners = new Set<() => void>()

function publishAnchors(anchors: TopBarAnchor[]) {
  currentAnchors = anchors
  listeners.forEach((l) => l())
}

function subscribe(cb: () => void) {
  listeners.add(cb)
  return () => {
    listeners.delete(cb)
  }
}

/**
 * Rendered by a page to publish its section anchors into the top bar.
 * Renders nothing; anchors clear when the page unmounts.
 */
export function SectionAnchors({ anchors }: { anchors: TopBarAnchor[] }) {
  // Key on the serialized list so a page can swap anchors without re-mounting.
  const key = JSON.stringify(anchors)
  useEffect(() => {
    publishAnchors(anchors)
    return () => publishAnchors(EMPTY)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  return null
}

/** Replays the lock-on sweep (see [data-lock-on] in tailwind.css) on the target card. */
function lockOn(id: string) {
  const el = document.getElementById(id)
  if (!el) return
  el.removeAttribute('data-lock-on')
  void el.offsetWidth // reflow so a re-click restarts the animation
  el.setAttribute('data-lock-on', '')
  el.addEventListener('animationend', function onEnd(e) {
    if (e.animationName !== 'rs-lock-fade') return
    el.removeAttribute('data-lock-on')
    el.removeEventListener('animationend', onEnd)
  })
}

/**
 * Bar above the content area: lists the page's section anchors, right-aligned.
 * Pages that publish no anchors get no bar — the page's own heading carries
 * the title. Background matches the sidebar.
 */
export function TopBar() {
  const t = useT()
  const anchors = useSyncExternalStore(
    subscribe,
    () => currentAnchors,
    () => EMPTY,
  )

  if (anchors.length === 0) return null

  return (
    <div className="border-line-strong bg-background sticky top-0 z-10 border-b px-6 max-lg:hidden lg:px-8">
      <div className="flex h-16 max-w-6xl items-center justify-end gap-6">
        <nav
          aria-label={t('Page sections')}
          className="flex min-w-0 items-center gap-5 overflow-x-auto"
        >
          {anchors.map((a) => (
            <a
              key={a.id}
              href={`#${a.id}`}
              onClick={() => lockOn(a.id)}
              className="hover:text-foreground flex shrink-0 items-center text-[11px] font-semibold tracking-[0.14em] whitespace-nowrap text-zinc-500 uppercase dark:text-zinc-400"
            >
              <span aria-hidden="true" className="bg-accent mr-1.5 inline-block size-1.5" />
              {t(a.label)}
            </a>
          ))}
        </nav>
      </div>
    </div>
  )
}

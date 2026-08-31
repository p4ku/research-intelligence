'use client'

import { SectionLabel } from '@/components/scanner-ui'
import { ChevronDownIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { useCallback, useEffect, useState } from 'react'

/**
 * Open/closed state persisted per section key. Starts from the default and
 * syncs from storage after mount, so server and client hydrate identically.
 */
function useStoredOpen(key: string, defaultOpen: boolean): [boolean, (v: boolean) => void] {
  const [open, setOpenState] = useState(defaultOpen)

  // Reading storage during render (useSyncExternalStore) breaks hydration of
  // the streamed page, so sync after mount instead — same as useStoredFlag.
  useEffect(() => {
    const stored = localStorage.getItem(key)
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (stored !== null) setOpenState(stored === '1')
  }, [key])

  const setOpen = useCallback(
    (v: boolean) => {
      localStorage.setItem(key, v ? '1' : '0')
      setOpenState(v)
    },
    [key],
  )
  return [open, setOpen]
}

/**
 * A page section that reveals its content on demand. The open/closed state
 * persists per section (localStorage), so the page stays customised the way
 * the user left it. Following a top-bar anchor to a closed section opens it.
 */
export function CollapsibleSection({
  id,
  label,
  meta,
  defaultOpen = false,
  children,
}: {
  id: string
  label: string
  /** Optional right-hand slot next to the toggle (e.g. a "view all" link). */
  meta?: React.ReactNode
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useStoredOpen(`rs-section-open:${id}`, defaultOpen)

  // A top-bar anchor pointing here should reveal the section, not just scroll to it.
  useEffect(() => {
    function onHash() {
      if (window.location.hash === `#${id}`) setOpen(true)
    }
    onHash()
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [id, setOpen])

  return (
    <section
      id={id}
      className="border-line-soft scroll-mt-28 border-t pt-4 first:border-t-0 first:pt-0"
    >
      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="group flex items-center gap-2"
        >
          <SectionLabel>{label}</SectionLabel>
          <ChevronDownIcon
            className={clsx(
              'size-4 text-zinc-400 transition-transform duration-200 ease-out group-hover:text-zinc-600 dark:group-hover:text-zinc-300',
              !open && '-rotate-90',
            )}
          />
        </button>
        {meta}
      </div>
      {/* Content stays mounted; grid-rows 0fr→1fr glides it open instead of
          teleporting it in. inert keeps the closed content out of the tab order. */}
      <div
        className={clsx(
          'grid transition-[grid-template-rows,opacity] duration-200 ease-out motion-reduce:transition-none',
          open ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0',
        )}
        inert={!open}
      >
        <div className="overflow-hidden">
          <div className="mt-3">{children}</div>
        </div>
      </div>
    </section>
  )
}

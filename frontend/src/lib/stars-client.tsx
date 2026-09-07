'use client'

import { bffFetch } from '@/lib/bff/client'
import {
  applyStar,
  emptyStars,
  type StarKind,
  type Stars,
  type StarUpdate,
} from '@/lib/bff/stars/schema'
import { useT } from '@/lib/i18n-client'
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

/**
 * The client's view of the user's stars: the last set the server confirmed
 * (seeded by the sidebar layout, re-seeded whenever the server re-renders)
 * with the not-yet-confirmed toggles applied on top. Writes go to
 * `PUT /bff/stars` one after another — the stub store is a read-modify-write
 * on the request cookie, so two overlapping PUTs would lose one — and each
 * echo replaces the confirmed set. A failed write drops its toggle and says
 * so; a write the server capped (the oldest star evicted) says so too.
 *
 * Without a provider (the Studio gallery, unit renders) the hooks are inert:
 * nothing is starred and toggling does nothing.
 */

interface StarsValue {
  stars: Stars
  isStarred: (kind: StarKind, id: string) => boolean
  toggle: (kind: StarKind, id: string) => void
}

const StarsContext = createContext<StarsValue>({
  stars: emptyStars,
  isStarred: () => false,
  toggle: () => {},
})

function has(stars: Stars, kind: StarKind, id: string): boolean {
  return (kind === 'paper' ? stars.papers : stars.briefings).includes(id)
}

function size(stars: Stars): number {
  return stars.papers.length + stars.briefings.length
}

export function StarsProvider({
  initial,
  children,
}: {
  initial: Stars
  children: React.ReactNode
}) {
  const t = useT()
  const [confirmed, setConfirmed] = useState(initial)
  const [pending, setPending] = useState<StarUpdate[]>([])
  // A server re-render hands in a fresh confirmed set (adjust-during-render,
  // not an effect). Pending toggles stay on top, so a star clicked just
  // before a refresh is not reverted by a cookie read that predates its PUT.
  const [prevInitial, setPrevInitial] = useState(initial)
  if (prevInitial !== initial) {
    setPrevInitial(initial)
    setConfirmed(initial)
  }
  const stars = useMemo(() => pending.reduce(applyStar, confirmed), [confirmed, pending])

  // The write queue, and the confirmed set as the queue's callbacks see it.
  const queue = useRef<Promise<unknown>>(Promise.resolve())
  const confirmedRef = useRef(confirmed)
  useEffect(() => {
    confirmedRef.current = confirmed
  }, [confirmed])

  const toggle = useCallback(
    (kind: StarKind, id: string) => {
      const update: StarUpdate = { kind, id, starred: !has(stars, kind, id) }
      setPending((p) => [...p, update])
      const settle = () => setPending((p) => p.filter((u) => u !== update))
      queue.current = queue.current
        .then(() => bffFetch<Stars>('/bff/stars', { method: 'PUT', body: JSON.stringify(update) }))
        .then(
          (next) => {
            // Smaller than the set we asked for: the store hit its cap and dropped the oldest star.
            const expected = applyStar(confirmedRef.current, update)
            if (size(next) < size(expected)) {
              toast.message(t('Star limit reached — the oldest star was removed.'))
            }
            confirmedRef.current = next
            setConfirmed(next)
            settle()
          },
          () => {
            settle()
            toast.error(t('Could not save the star. Try again.'))
          },
        )
    },
    [stars, t],
  )

  const value = useMemo<StarsValue>(
    () => ({ stars, isStarred: (kind, id) => has(stars, kind, id), toggle }),
    [stars, toggle],
  )
  return <StarsContext.Provider value={value}>{children}</StarsContext.Provider>
}

export function useStars(): StarsValue {
  return useContext(StarsContext)
}

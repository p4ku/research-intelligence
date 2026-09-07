'use client'

import { bffFetch } from '@/lib/bff/client'
import { applyStar, emptyStars, type StarKind, type Stars } from '@/lib/bff/stars/schema'
import { useT } from '@/lib/i18n-client'
import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

/**
 * The client's view of the user's stars: seeded by the sidebar layout from
 * the stars service, toggled optimistically through `PUT /bff/stars`, and
 * re-seeded whenever the server re-renders (the cookie / backend is the
 * source of truth between navigations). One provider per shell, so every
 * star on a page — card corner, header, filter chip — reads the same set.
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

export function StarsProvider({
  initial,
  children,
}: {
  initial: Stars
  children: React.ReactNode
}) {
  const t = useT()
  const [stars, setStars] = useState(initial)
  // A server re-render hands in a fresh set (adjust-during-render, not an effect).
  const [prevInitial, setPrevInitial] = useState(initial)
  if (prevInitial !== initial) {
    setPrevInitial(initial)
    setStars(initial)
  }
  // A sequence so a slow response can never overwrite a newer optimistic state.
  const seq = useRef(0)

  const toggle = useCallback(
    (kind: StarKind, id: string) => {
      const update = { kind, id, starred: !has(stars, kind, id) }
      const mine = ++seq.current
      setStars((s) => applyStar(s, update))
      bffFetch<Stars>('/bff/stars', { method: 'PUT', body: JSON.stringify(update) })
        .then((next) => {
          if (mine === seq.current) setStars(next)
        })
        .catch(() => {
          if (mine === seq.current)
            setStars((s) => applyStar(s, { ...update, starred: !update.starred }))
          toast.error(t('Could not save the star. Try again.'))
        })
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

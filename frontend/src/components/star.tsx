'use client'

import type { StarKind } from '@/lib/bff/stars/schema'
import { useT } from '@/lib/i18n-client'
import { useStars } from '@/lib/stars-client'
import clsx from 'clsx'
import { StarIcon } from 'lucide-react'
import { useState } from 'react'

/**
 * The star, in its three homes. Quiet by design: an outline that waits for
 * the row to be hovered (or focused, or already starred — and always on a
 * touch screen, which cannot hover), fills Zitrus with one overshoot when
 * pressed, and never moves anything around it. Starred ink is `warn-ink`
 * over a `warn` fill: the fill is the signal, the darker edge keeps the
 * glyph readable on white (docs/design.md: Zitrus text always via warn-ink).
 *
 * - `StarButton`  — the icon in a card or row corner. The parent carries
 *   `group relative`; the button positions itself with `className`.
 * - `StarToggle`  — the labelled ghost button a page header wears.
 * - `StarredChip` — the list filter: "Starred · n".
 *
 * Every control is a toggle button: `aria-pressed` carries the state, the
 * name stays constant ("Star this paper" / the visible label), so a screen
 * reader never hears "unstar … pressed".
 */

const POP_MS = 300

/** The one-overshoot fill: armed on every star, cleared on a timer (reduced motion never fires animationend). */
function usePop(): [boolean, () => void] {
  const [pop, setPop] = useState(false)
  return [
    pop,
    () => {
      setPop(true)
      window.setTimeout(() => setPop(false), POP_MS)
    },
  ]
}

const ON_ICON = 'text-warn-ink fill-warn'

export function StarButton({
  kind,
  id,
  className,
}: {
  kind: StarKind
  id: string
  className?: string
}) {
  const t = useT()
  const { isStarred, toggle } = useStars()
  const on = isStarred(kind, id)
  const [pop, arm] = usePop()
  return (
    <button
      type="button"
      aria-pressed={on}
      aria-label={kind === 'paper' ? t('Star this paper') : t('Star this briefing')}
      title={on ? t('Starred') : t('Star')}
      onClick={() => {
        if (!on) arm()
        toggle(kind, id)
      }}
      className={clsx(
        'inline-flex size-7 items-center justify-center rounded-sm text-zinc-400 transition-[opacity,color,transform] duration-150 ease-out',
        // Hidden until the row is hovered or focused; always shown once starred,
        // and always on coarse pointers, where there is no hover to reveal it.
        'opacity-0 group-focus-within:opacity-100 group-hover:opacity-100 focus-visible:opacity-100 aria-pressed:opacity-100 pointer-coarse:opacity-100',
        'aria-pressed:text-warn-ink hover:text-zinc-700 dark:hover:text-zinc-200',
        className,
      )}
    >
      <StarIcon
        aria-hidden="true"
        strokeWidth={1.75}
        className={clsx(
          'size-4',
          on && 'fill-warn',
          pop && 'animate-star-pop motion-reduce:animate-none',
        )}
      />
    </button>
  )
}

export function StarToggle({
  kind,
  id,
  className,
}: {
  kind: StarKind
  id: string
  className?: string
}) {
  const t = useT()
  const { isStarred, toggle } = useStars()
  const on = isStarred(kind, id)
  const [pop, arm] = usePop()
  const label = on ? t('Starred') : kind === 'paper' ? t('Star paper') : t('Star briefing')
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={() => {
        if (!on) arm()
        toggle(kind, id)
      }}
      className={clsx(
        'border-line bg-surface inline-flex h-[30px] shrink-0 items-center gap-1.5 rounded-sm border px-2.5 text-xs font-medium whitespace-nowrap text-zinc-600 transition-colors duration-150 ease-out',
        'hover:border-zinc-400 hover:text-zinc-950 active:scale-[0.98] aria-pressed:text-zinc-950',
        'dark:text-zinc-300 dark:hover:border-zinc-500 dark:hover:text-white dark:aria-pressed:text-white',
        className,
      )}
    >
      <StarIcon
        aria-hidden="true"
        strokeWidth={2}
        className={clsx(
          'size-3.5 transition-colors duration-150 ease-out',
          // A ternary, not two colour utilities: same specificity, sheet order would decide.
          on ? ON_ICON : 'text-zinc-400',
          pop && 'animate-star-pop motion-reduce:animate-none',
        )}
      />
      {label}
    </button>
  )
}

export function StarredChip({
  active,
  count,
  onToggle,
  className,
}: {
  active: boolean
  count: number
  onToggle: () => void
  className?: string
}) {
  const t = useT()
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onToggle}
      className={clsx(
        'inline-flex h-6 items-center gap-1.5 rounded-full border bg-white pr-2.5 pl-2 text-xs transition-colors duration-150 ease-out dark:bg-zinc-900',
        active
          ? 'border-zinc-950 text-zinc-950 dark:border-white dark:text-white'
          : 'border-zinc-950/10 text-zinc-600 hover:border-zinc-400 dark:border-white/10 dark:text-zinc-300 dark:hover:border-zinc-500',
        className,
      )}
    >
      <StarIcon
        aria-hidden="true"
        strokeWidth={2}
        className={clsx('size-3', active ? ON_ICON : 'text-zinc-400')}
      />
      {t('Starred')}
      <span className={clsx('font-mono tabular-nums', !active && 'text-zinc-400')}>{count}</span>
    </button>
  )
}

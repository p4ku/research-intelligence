'use client'

import type { StarKind } from '@/lib/bff/stars/schema'
import { useFeatures } from '@/lib/features-client'
import { formatNumber } from '@/lib/i18n'
import { useLanguage, useT } from '@/lib/i18n-client'
import { useStars } from '@/lib/stars-client'
import clsx from 'clsx'
import { StarIcon } from 'lucide-react'
import { useState } from 'react'

/**
 * The star, in its three homes. Quiet by design: an outline that waits for
 * the row to be hovered (or focused, or already starred), fills Zitrus with
 * one overshoot when pressed, and never moves anything around it.
 *
 * - `StarButton`  — the icon in a card or row corner. The parent carries
 *   `group relative`; the button positions itself with `className`.
 * - `StarToggle`  — the labelled ghost button a page header wears.
 * - `StarredChip` — the list filter: "Starred · n".
 *
 * All three carry a belt-and-braces `stars` flag guard, and it sits *after*
 * every hook, immediately before the JSX: a flip re-renders mounted instances
 * rather than unmounting them, so an early return above the hooks would be a
 * rules-of-hooks error at lint time and "Rendered fewer hooks than expected"
 * live. The braces are the call sites, which withhold the element itself —
 * three of them must, for layout (docs/design/feature-flags.md §4.2).
 */

function useStarLabels(kind: StarKind, on: boolean) {
  const t = useT()
  const action =
    kind === 'paper'
      ? on
        ? t('Unstar this paper')
        : t('Star this paper')
      : on
        ? t('Unstar this briefing')
        : t('Star this briefing')
  return { action, state: on ? t('Starred') : t('Star') }
}

/** The one-overshoot fill; re-armed on every star, cleared when it ends. */
function usePop(): [boolean, () => void, () => void] {
  const [pop, setPop] = useState(false)
  return [pop, () => setPop(true), () => setPop(false)]
}

export function StarButton({
  kind,
  id,
  className,
}: {
  kind: StarKind
  id: string
  className?: string
}) {
  const { isStarred, toggle } = useStars()
  const on = isStarred(kind, id)
  const { action, state } = useStarLabels(kind, on)
  const [pop, arm, settle] = usePop()
  const { stars } = useFeatures()
  if (!stars) return null
  return (
    <button
      type="button"
      aria-pressed={on}
      aria-label={action}
      title={state}
      onClick={(e) => {
        // Inside a linked card: the star must not follow the link.
        e.preventDefault()
        e.stopPropagation()
        if (!on) arm()
        toggle(kind, id)
      }}
      className={clsx(
        'inline-flex size-7 items-center justify-center rounded-sm text-zinc-400 transition-[opacity,color] duration-150 ease-out',
        'opacity-0 group-focus-within:opacity-100 group-hover:opacity-100 focus-visible:opacity-100 aria-pressed:opacity-100 pointer-coarse:opacity-100',
        'hover:text-zinc-700 aria-pressed:text-warn dark:hover:text-zinc-200',
        className,
      )}
    >
      <StarIcon
        aria-hidden="true"
        strokeWidth={1.75}
        onAnimationEnd={settle}
        className={clsx(
          'size-4',
          on && 'fill-current',
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
  const { action } = useStarLabels(kind, on)
  const [pop, arm, settle] = usePop()
  const idle = kind === 'paper' ? t('Star paper') : t('Star briefing')
  const { stars } = useFeatures()
  if (!stars) return null
  return (
    <button
      type="button"
      aria-pressed={on}
      aria-label={action}
      onClick={() => {
        if (!on) arm()
        toggle(kind, id)
      }}
      className={clsx(
        'group inline-flex h-[30px] shrink-0 items-center gap-1.5 rounded-sm border border-line bg-surface px-2.5 text-xs font-medium whitespace-nowrap text-zinc-600 transition-colors duration-150 ease-out',
        'hover:border-zinc-400 hover:text-zinc-950 active:scale-[0.98] aria-pressed:text-zinc-950',
        'dark:text-zinc-300 dark:hover:border-zinc-500 dark:hover:text-white dark:aria-pressed:text-white',
        className,
      )}
    >
      <StarIcon
        aria-hidden="true"
        strokeWidth={2}
        onAnimationEnd={settle}
        className={clsx(
          'size-3.5 text-zinc-400 transition-colors duration-150 ease-out',
          on && 'fill-current text-warn',
          pop && 'animate-star-pop motion-reduce:animate-none',
        )}
      />
      {/* Both labels occupy the same cell, so toggling never moves the page. */}
      <span className="grid">
        <span aria-hidden={on} className={clsx('col-start-1 row-start-1', on && 'invisible')}>
          {idle}
        </span>
        <span aria-hidden={!on} className={clsx('col-start-1 row-start-1', !on && 'invisible')}>
          {t('Starred')}
        </span>
      </span>
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
  const { lang } = useLanguage()
  const { stars } = useFeatures()
  if (!stars) return null
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
        className={clsx('size-3', active ? 'fill-current text-warn' : 'text-zinc-400')}
      />
      {t('Starred')}
      <span className={clsx('font-mono tabular-nums', !active && 'text-zinc-400')}>
        {formatNumber(count, lang)}
      </span>
    </button>
  )
}

import { Bone } from '@/components/skeleton'
import { ALL_ON, type Features } from '@/lib/features'
import { fmt, formatNumber, type Lang, type T } from '@/lib/i18n'
import { ChevronLeftIcon, ChevronRightIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import Link from 'next/link'
import type { ReactNode } from 'react'

/**
 * The row above the record: back to the list on the left, previous / next
 * paper on the right. Neighbours follow the domain's papers in signal order
 * (the list's default sort); a paper outside that order — rejected, unscored
 * — keeps the back link and loses the arrows.
 *
 * Opened from a briefing (`?run=` in the URL) the row is that briefing's:
 * `back` returns to the edition and the arrows walk its papers in the order
 * the briefing lists them, whatever `all_papers` says — the briefing is a
 * destination the reader can always open. The pager shows whenever there is
 * a briefing or a list to return to.
 *
 * With `all_papers` off and no briefing, the list is not a destination: the
 * pager and the "{n} of {total}" position go (they are claims about a list
 * the reader can no longer open) and the back link points at Briefings, but
 * the row itself stays — with the crumb trail gone too, it is the paper's
 * only exit. `features` defaults to ALL_ON because the skeleton gallery
 * renders these three with no such prop; the flag reaches them from
 * PaperRecord and loading.tsx.
 *
 * Briefings is a choice, not the only reading: the design doc leaves the
 * redirected destination open between `/briefing` (`Go to Briefings`) and
 * `/dashboard` (`Back to Today`, already German in `de/chrome.ts`). Briefings
 * is chosen here to match the button the not-found card promotes when the flag
 * is off, so every flag-off exit lands in the same place. Changing it is three
 * lines — the loaded row and the skeleton below, and papers/[id]/error.tsx —
 * and all three move together, or the exit says one thing and the error
 * boundary another.
 *
 * One note for whoever writes the flag-off e2e spec: with `all_papers` off
 * this row is an <a href="/briefing"> inside a <nav>, which matches two
 * members of the SidebarNav.navBriefing union (tests_e2e/pages/SidebarNav.ts).
 * Assert this exit with a scoped locator — [data-shape="paper-nav"]
 * a[href="/briefing"] — never through the sidebar page object.
 */

export interface PaperNeighbours {
  prev: string | null
  next: string | null
  /** 1-based position and the size of the ordered list. */
  position: number
  total: number
}

/** Where the back link leads and what it says. */
export interface PaperExit {
  href: string
  label: string
}

/** The exit for a paper opened on its own: the list, or Briefings when the list is hidden. */
function defaultExit(features: Features, t: T): PaperExit {
  return features.all_papers
    ? { href: '/papers', label: t('All papers') }
    : { href: '/briefing', label: t('Go to Briefings') }
}

const BTN =
  'inline-flex h-[30px] items-center gap-1.5 rounded-sm px-2.5 text-[13px] font-medium text-zinc-600 transition-colors duration-150 ease-out dark:text-zinc-300'
const LIVE = 'hover:bg-foreground/6 hover:text-zinc-950 dark:hover:text-white'
const DEAD = 'cursor-default text-zinc-400 opacity-60 dark:text-zinc-500'

export function PaperNavFrame({
  state = 'loaded',
  back,
  prev,
  position,
  next,
  pager,
}: {
  state?: 'loaded' | 'skeleton'
  back: ReactNode
  prev: ReactNode
  position: ReactNode
  next: ReactNode
  /** Whether there is a list or briefing to page through. */
  pager: boolean
}) {
  return (
    <nav
      data-shape="paper-nav"
      data-state={state}
      className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2"
    >
      <div data-row="back">{back}</div>
      {/* The whole div, not just its contents: an empty pager still holds its
          12px position span opposite the back link under justify-between. */}
      {pager && (
        <div data-row="pager" className="flex items-center gap-1">
          {prev}
          <span className="px-1.5 font-mono text-xs text-zinc-400 tabular-nums">{position}</span>
          {next}
        </div>
      )}
    </nav>
  )
}

function Arrow({ href, dir, label }: { href: string | null; dir: 'prev' | 'next'; label: string }) {
  const icon =
    dir === 'prev' ? (
      <ChevronLeftIcon aria-hidden="true" className="size-4" />
    ) : (
      <ChevronRightIcon aria-hidden="true" className="size-4" />
    )
  if (!href) {
    return (
      <span aria-disabled="true" className={clsx(BTN, DEAD)}>
        {dir === 'prev' && icon}
        {label}
        {dir === 'next' && icon}
      </span>
    )
  }
  return (
    <Link href={href} className={clsx(BTN, LIVE)}>
      {dir === 'prev' && icon}
      {label}
      {dir === 'next' && icon}
    </Link>
  )
}

export function PaperNav({
  neighbours,
  t,
  lang = 'en',
  features = ALL_ON,
  back,
}: {
  neighbours: PaperNeighbours | null
  t: T
  lang?: Lang
  features?: Features
  /** The briefing the paper was opened from; absent, the list is the exit. */
  back?: PaperExit
}) {
  const n = neighbours
  const exit = back ?? defaultExit(features, t)
  return (
    <PaperNavFrame
      pager={features.all_papers || Boolean(back)}
      back={
        <Link href={exit.href} className={clsx(BTN, LIVE, '-ml-2.5')}>
          <ChevronLeftIcon aria-hidden="true" className="size-4" />
          {exit.label}
        </Link>
      }
      prev={<Arrow href={n?.prev ?? null} dir="prev" label={t('Previous paper')} />}
      position={
        n && typeof n.position === 'number' && typeof n.total === 'number'
          ? fmt(t('{n} of {total}'), {
              n: formatNumber(n.position, lang),
              total: formatNumber(n.total, lang),
            })
          : '—'
      }
      next={<Arrow href={n?.next ?? null} dir="next" label={t('Next paper')} />}
    />
  )
}

export function PaperNavSkeleton({
  t,
  features = ALL_ON,
  back,
}: {
  t: T
  features?: Features
  /** The back label the loaded row will show when the URL names a briefing. */
  back?: string
}) {
  const label = back ?? defaultExit(features, t).label
  return (
    <PaperNavFrame
      state="skeleton"
      pager={features.all_papers || Boolean(back)}
      back={
        // The same label as the loaded row: two different words are two
        // different widths, and the back slot would reflow on every load.
        <span className={clsx(BTN, '-ml-2.5')}>
          <ChevronLeftIcon aria-hidden="true" className="size-4" />
          {label}
        </span>
      }
      prev={<Arrow href={null} dir="prev" label={t('Previous paper')} />}
      position={<Bone.Number digits={7} />}
      next={<Arrow href={null} dir="next" label={t('Next paper')} />}
    />
  )
}

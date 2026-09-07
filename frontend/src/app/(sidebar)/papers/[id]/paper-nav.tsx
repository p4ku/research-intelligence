import { Bone } from '@/components/skeleton'
import { fmt, type T } from '@/lib/i18n'
import { ChevronLeftIcon, ChevronRightIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import Link from 'next/link'
import type { ReactNode } from 'react'

/**
 * The row above the record: back to the list on the left, previous / next
 * paper on the right. Neighbours follow the domain's papers in signal order
 * (the list's default sort); a paper outside that order — rejected, unscored
 * — keeps the back link and loses the arrows.
 */

export interface PaperNeighbours {
  prev: string | null
  next: string | null
  /** 1-based position and the size of the ordered list. */
  position: number
  total: number
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
}: {
  state?: 'loaded' | 'skeleton'
  back: ReactNode
  prev: ReactNode
  position: ReactNode
  next: ReactNode
}) {
  return (
    <nav
      data-shape="paper-nav"
      data-state={state}
      className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2"
    >
      <div data-row="back">{back}</div>
      <div data-row="pager" className="flex items-center gap-1">
        {prev}
        <span className="px-1.5 font-mono text-xs text-zinc-400 tabular-nums">{position}</span>
        {next}
      </div>
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

export function PaperNav({ neighbours, t }: { neighbours: PaperNeighbours | null; t: T }) {
  const n = neighbours
  return (
    <PaperNavFrame
      back={
        <Link href="/papers" className={clsx(BTN, LIVE, '-ml-2.5')}>
          <ChevronLeftIcon aria-hidden="true" className="size-4" />
          {t('All papers')}
        </Link>
      }
      prev={<Arrow href={n?.prev ?? null} dir="prev" label={t('Previous paper')} />}
      position={n ? fmt(t('{n} of {total}'), { n: n.position, total: n.total }) : '—'}
      next={<Arrow href={n?.next ?? null} dir="next" label={t('Next paper')} />}
    />
  )
}

export function PaperNavSkeleton({ t }: { t: T }) {
  return (
    <PaperNavFrame
      state="skeleton"
      back={
        <span className={clsx(BTN, '-ml-2.5')}>
          <ChevronLeftIcon aria-hidden="true" className="size-4" />
          {t('All papers')}
        </span>
      }
      prev={<Arrow href={null} dir="prev" label={t('Previous paper')} />}
      position={<Bone.Number digits={7} />}
      next={<Arrow href={null} dir="next" label={t('Next paper')} />}
    />
  )
}

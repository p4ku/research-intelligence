'use client'

import clsx from 'clsx'
import { useEffect, useState, type MouseEvent, type ReactNode } from 'react'

/**
 * The rail's bars: one per definition, each a link to that definition's
 * article in the column. The bar of the article under the reading line is
 * marked, so the rail says where the reader is as well as how the paper
 * scored. Client-side for the two things only a browser knows — where the
 * page is scrolled to, and whether motion is wanted — while ScoreBarFrame
 * stays a plain row the skeleton can render without a link.
 */

export interface RailBar {
  key: string
  label: string
  /** The article id the bar links to. */
  anchor: string
  /** 0–1, or null when the dimension has no scale. */
  pct: number | null
  value: ReactNode
}

// A section counts as being read once its top has passed this line.
const READING_LINE = 120

const ROW =
  'grid grid-cols-[96px_minmax(0,1fr)_36px] items-center gap-2.5 py-1 text-xs text-zinc-600 dark:text-zinc-300'

export function ScoreBarFrame({
  label,
  fill,
  value,
  href,
  active = false,
  onClick,
}: {
  label: ReactNode
  /** The track's fill; the skeleton leaves the track empty. */
  fill?: ReactNode
  value: ReactNode
  /** With a target the row is a link; the skeleton has none. */
  href?: string
  active?: boolean
  onClick?: (e: MouseEvent<HTMLAnchorElement>) => void
}) {
  const inner = (
    <>
      <span className="truncate">{label}</span>
      <span className="block h-1 w-full overflow-hidden bg-line-soft">{fill}</span>
      <span className="text-right font-mono font-medium text-zinc-950 tabular-nums dark:text-white">
        {value}
      </span>
    </>
  )
  return (
    <li data-row="bar">
      {href ? (
        <a
          href={href}
          onClick={onClick}
          aria-current={active ? 'location' : undefined}
          className={clsx(
            ROW,
            '-mx-2 rounded-sm px-2 transition-colors duration-150 ease-out hover:bg-line-soft hover:text-zinc-950 dark:hover:text-white',
            active && 'font-semibold text-zinc-950 dark:text-white',
          )}
        >
          {inner}
        </a>
      ) : (
        <span className={ROW}>{inner}</span>
      )}
    </li>
  )
}

export function ScoreBars({ bars }: { bars: RailBar[] }) {
  const [active, setActive] = useState<string | null>(null)
  const anchors = bars.map((b) => b.anchor).join(' ')

  useEffect(() => {
    let frame = 0
    const measure = () => {
      frame = 0
      let current: string | null = null
      for (const anchor of anchors.split(' ')) {
        const el = document.getElementById(anchor)
        if (el && el.getBoundingClientRect().top <= READING_LINE) current = anchor
      }
      setActive(current)
    }
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(measure)
    }
    measure()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      if (frame) cancelAnimationFrame(frame)
    }
  }, [anchors])

  const go = (anchor: string) => (e: MouseEvent<HTMLAnchorElement>) => {
    const el = document.getElementById(anchor)
    if (!el) return
    e.preventDefault()
    el.scrollIntoView({
      behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
      block: 'start',
    })
    history.replaceState(null, '', `#${anchor}`)
  }

  return (
    <>
      {bars.map((b) => (
        <ScoreBarFrame
          key={b.key}
          href={`#${b.anchor}`}
          active={active === b.anchor}
          onClick={go(b.anchor)}
          label={b.label}
          fill={
            b.pct !== null && (
              // scaleX rather than width so the glide runs off the main thread
              <span
                className="block h-full w-full origin-left bg-accent transition-transform duration-[250ms] ease-out"
                style={{ transform: `scaleX(${b.pct})` }}
              />
            )
          }
          value={b.value}
        />
      ))}
    </>
  )
}

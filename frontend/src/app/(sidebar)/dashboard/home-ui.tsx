import { SignalScore } from '@/components/scanner-ui'
import { Bone } from '@/components/skeleton'
import type { Lang, T } from '@/lib/i18n'
import clsx from 'clsx'
import Link from 'next/link'
import type { ReactNode } from 'react'

/**
 * Small pieces Home's ledger and the masthead (gallery only since 7 Sep
 * 2026) share. No directive: the masthead renders on the server, the ledger
 * on the client, and both use these.
 */

/**
 * Home's two-column frame: Recent Briefings beside New Briefing.
 *
 * No breakpoint. The two are flex items whose widths are stated in `rem` —
 * the ledger asks for 43rem, about what its seven columns need before they
 * start wrapping, the card for 18rem — and they sit side by side exactly
 * while both fit, wrapping onto separate rows when they do not. A viewport
 * breakpoint could not do this honestly: it is a fixed pixel number, and a
 * reader on Chrome's larger font setting needs *more* width for the same
 * table, so a `min-[1400px]` rule hands the ledger less room precisely when
 * it needs more, and the last column goes back outside the panel. Stated in
 * rem, the whole arrangement scales with the reader's text.
 *
 * Both grow into whatever is left over, so nothing is stranded: side by side
 * the ledger takes most of the slack, and wrapped, the card fills its row up
 * to a form's comfortable measure rather than a page's.
 *
 * The loaded section and its skeleton both render through here, so the two
 * cannot drift.
 */
const LEDGER = 'min-w-0 grow basis-[43rem]'
const CARD = 'grow basis-72 max-w-sm'

export function HomeGrid({
  ledger,
  card,
  children,
}: {
  ledger: ReactNode
  card?: ReactNode
  /** Anything that renders nothing but belongs to the section (the live refresh). */
  children?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-start gap-8">
      <div className={clsx(LEDGER, !card && 'basis-full')}>{ledger}</div>
      {card ? <aside className={CARD}>{card}</aside> : null}
      {children}
    </div>
  )
}

/** One of the strongest papers in a briefing, as Home lists it. */
export interface HomePaper {
  id: string
  /** The paper as this briefing's run read it — `paperHref` with the run, so the page shows the score listed here. */
  href: string
  title: string
  /** Already worded ("A. Okafor, B. Lindqvist et al."). */
  authors: string
  score: number | null
}

export function TextLink({
  href,
  children,
  className,
}: {
  href: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <Link
      href={href}
      className={clsx(
        'text-xs font-medium text-blue-600 hover:underline dark:text-blue-400',
        className,
      )}
    >
      {children}
    </Link>
  )
}

/** The exit the spec puts beside Recent Briefings. */
export function HomeLinks({ t, className }: { t: T; className?: string }) {
  return (
    <span className={clsx('flex items-baseline', className)}>
      <TextLink href="/briefing">{t('All briefings →')}</TextLink>
    </span>
  )
}

/* ------------------------------- Top papers ------------------------------ */

function TopPapersFrame({
  items,
  dense,
  wrap,
  className,
}: {
  items: React.ReactNode[]
  dense: boolean
  wrap: boolean
  className?: string
}) {
  return (
    <ol className={clsx(dense ? 'space-y-2' : 'space-y-3', className)}>
      {items.map((item, i) => (
        <li
          key={i}
          data-row="paper"
          className={clsx('flex', wrap ? 'items-start' : 'items-center', dense ? 'gap-3' : 'gap-4')}
        >
          {item}
        </li>
      ))}
    </ol>
  )
}

/**
 * The strongest papers: score ring, title, authors — each a link to the
 * paper. `wrap` allows two title lines for narrow columns; otherwise one
 * truncated line.
 */
export function TopPapers({
  papers,
  dense = false,
  wrap = false,
  className,
  lang = 'en',
}: {
  papers: HomePaper[]
  dense?: boolean
  wrap?: boolean
  className?: string
  /** For the score ring's figure; a prop, since the masthead renders on the server. */
  lang?: Lang
}) {
  return (
    <TopPapersFrame
      dense={dense}
      wrap={wrap}
      className={className}
      items={papers.map((p) => (
        <>
          <SignalScore score={p.score} size="sm" lang={lang} />
          <Link
            href={p.href}
            className="min-w-0 flex-1 text-sm font-medium text-zinc-900 hover:underline dark:text-zinc-100"
          >
            <span
              className={clsx('block', wrap ? 'line-clamp-2 leading-snug' : 'truncate')}
              title={p.title}
            >
              {p.title}
            </span>
            <span className="block truncate text-xs font-normal text-zinc-500 dark:text-zinc-400">
              {p.authors}
            </span>
          </Link>
        </>
      ))}
    />
  )
}

export function TopPapersSkeleton({
  count = 3,
  dense = false,
  wrap = false,
  className,
}: {
  count?: number
  dense?: boolean
  wrap?: boolean
  className?: string
}) {
  return (
    <TopPapersFrame
      dense={dense}
      wrap={wrap}
      className={className}
      items={Array.from({ length: count }, (_, i) => (
        <>
          <Bone.Ring size={40} />
          <span className="min-w-0 flex-1 text-sm font-medium">
            <span className={clsx('block', wrap && 'leading-snug')}>
              <Bone.Text lines={wrap ? 2 : 1} widths={wrap ? ['92%', '58%'] : ['84%']} />
            </span>
            <span className="block text-xs font-normal">
              <Bone.Text widths={[i % 2 ? '38%' : '46%']} />
            </span>
          </span>
        </>
      ))}
    />
  )
}

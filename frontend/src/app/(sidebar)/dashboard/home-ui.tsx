import { SignalScore } from '@/components/scanner-ui'
import { Bone } from '@/components/skeleton'
import type { T } from '@/lib/i18n'
import clsx from 'clsx'
import Link from 'next/link'

/**
 * Small pieces Home's sections share. No directive: the masthead renders on
 * the server, the ledger on the client, and both use these.
 */

/** One of the strongest papers in a briefing, as Home lists it. */
export interface HomePaper {
  id: string
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
      <TextLink href="/briefing">{t('all briefings')}</TextLink>
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
}: {
  papers: HomePaper[]
  dense?: boolean
  wrap?: boolean
  className?: string
}) {
  return (
    <TopPapersFrame
      dense={dense}
      wrap={wrap}
      className={className}
      items={papers.map((p) => (
        <>
          <SignalScore score={p.score} size="sm" />
          <Link
            href={`/papers/${p.id}`}
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

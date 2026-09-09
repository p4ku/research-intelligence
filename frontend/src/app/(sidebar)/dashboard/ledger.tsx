'use client'

import { AnswerMarkdown } from '@/components/answer-markdown'
import { Bone } from '@/components/skeleton'
import { StarButton } from '@/components/star'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/table'
import { bffFetch } from '@/lib/bff/client'
import type { StartRun } from '@/lib/bff/pipeline-runs/schema'
import { errorsFromSubmit } from '@/lib/bff/problem-copy'
import { DEFAULT_FEATURES, type Features } from '@/lib/features'
import { useFeatures } from '@/lib/features-client'
import { fmt } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import clsx from 'clsx'
import { ChevronRightIcon } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useState, useTransition, type ReactNode } from 'react'
import { TextLink, TopPapers, type HomePaper } from './home-ui'

/**
 * Recent Briefings: the newest briefings across the user's domains, newest
 * first — the head of the Briefings archive, and shaped as its rows are. A
 * briefing's row is a link: click it anywhere and the briefing opens. The
 * disclosure triangle at its start is the other path — press it and the
 * brief and top three papers unfold beneath the cells, one row at a time,
 * without leaving the page; the star beside it marks the briefing. A run
 * still processing, or one that failed, keeps its place in the list without
 * a link — there is nothing to open yet — and a failed row offers Retry,
 * which resends the run's own parameters. A run that completed with nothing
 * to brief is not a briefing, so it is not a row (data.ts).
 */

export type RowStatus = 'current' | 'done' | 'processing' | 'failed'

export interface HomeBrief {
  /** The edition's permalink. */
  href: string
  inBrief: string
  screened: number
  included: number
  top: HomePaper[]
}

export interface HomeRow {
  id: string
  domain: string
  status: RowStatus
  /** The search window, already worded ("1 Aug–5 Sep 2026", "Last 7 days"). */
  period: string
  /** The completion day, already worded; null until the run completes. */
  generated: string | null
  /**
   * "12:03 UTC" — the completion clock, set only when the domain briefed
   * more than once that day, so the two rows read apart (in the Generated
   * cell and in the row's accessible name); null otherwise.
   */
  stamp?: string | null
  /** "07:12" — when the run started (UTC), for a row still processing. */
  startedClock: string | null
  /** The day the run failed, already worded; null unless it failed. */
  failedDay: string | null
  /** Papers in the briefing; null while processing or after a failure. */
  papers: number | null
  /** What Retry resends — the failed run's own parameters. */
  retry: StartRun | null
  /** The briefing behind the row — every completed row has one; null while processing or failed. */
  brief: HomeBrief | null
}

/**
 * The leading control columns Home and the archive share: a 28px triangle,
 * then a 28px star, each no wider than its control — the pair costs the row
 * 56px, and Home, beside the run card, has none to spare.
 */
export const LEAD = {
  expand: { head: 'w-7 pr-0!', cell: 'w-7 pr-0!' },
  star: { head: 'w-7 px-0!', cell: 'w-7 px-0!' },
} as const

// One entry per column: the classes of its header and body cells. Both the
// loaded table and its skeleton render from this list, so they cannot drift.
const COL = {
  expand: LEAD.expand,
  star: LEAD.star,
  domain: { head: '', cell: 'font-medium' },
  period: { head: '', cell: 'font-mono text-xs text-zinc-600 tabular-nums dark:text-zinc-300' },
  generated: {
    head: '',
    cell: 'font-mono text-xs text-zinc-500 tabular-nums dark:text-zinc-400',
  },
  papers: { head: 'text-right', cell: 'text-right font-mono tabular-nums' },
  status: { head: 'text-right', cell: 'text-right' },
} as const

const COLUMNS = ['expand', 'star', 'domain', 'period', 'generated', 'papers', 'status'] as const

/**
 * The columns this render has. With `stars` off the star column leaves the
 * list entirely rather than rendering an empty cell: header, body cells,
 * skeleton footprint and the expanded brief's colSpan all follow from here.
 */
function columnsFor(stars: boolean): readonly (typeof COLUMNS)[number][] {
  return stars ? COLUMNS : COLUMNS.filter((key) => key !== 'star')
}

function LedgerFrame({
  rows,
  state,
  stars,
}: {
  rows: ReactNode
  state: 'loaded' | 'skeleton'
  /** Whether this render has the star column — one source per tree, never the context twice. */
  stars: boolean
}) {
  const t = useT()
  const labels: Record<(typeof COLUMNS)[number], ReactNode> = {
    expand: <LeadHeading>{t('Show brief')}</LeadHeading>,
    star: <LeadHeading>{t('Star')}</LeadHeading>,
    domain: t('Domain'),
    period: t('Period'),
    generated: t('Generated'),
    papers: t('Papers'),
    status: '',
  }
  return (
    <Table dense data-shape="home-ledger" data-state={state}>
      <TableHead>
        <TableRow>
          {columnsFor(stars).map((key) => (
            <TableHeader key={key} className={COL[key].head}>
              {labels[key]}
            </TableHeader>
          ))}
        </TableRow>
      </TableHead>
      <TableBody>{rows}</TableBody>
    </Table>
  )
}

/* -------------------------------- Status -------------------------------- */

const STATUS_CLASS: Record<Exclude<RowStatus, 'done'>, { text: string; mark: string }> = {
  current: { text: 'text-blue-700 dark:text-accent', mark: 'bg-accent' },
  processing: { text: 'text-warn-ink dark:text-warn', mark: 'bg-warn animate-pulse rounded-full' },
  failed: { text: 'text-negative', mark: 'bg-negative' },
}

/** Latest · Processing · Failed; completed briefings that are not the latest carry none. */
/**
 * The Generated cell: the completion day, and the clock when the domain
 * briefed more than once that day. Home and the archive render it alike.
 */
export function Generated({ day, stamp }: { day: string; stamp: string | null }) {
  return stamp ? (
    <>
      {day}
      <span className="text-zinc-400"> · {stamp}</span>
    </>
  ) : (
    day
  )
}

/** The row link's accessible name; the clock joins it when two rows would otherwise read alike. */
export function rowTitle(
  row: { domain: string; period: string; stamp?: string | null },
  t: (s: string) => string,
): string {
  const base = `${t('Open briefing')}: ${row.domain}, ${row.period}`
  return row.stamp ? `${base}, ${row.stamp}` : base
}

export function StatusLabel({ status }: { status: RowStatus }) {
  const t = useT()
  if (status === 'done') return null
  const s = STATUS_CLASS[status]
  const label =
    status === 'current' ? t('Latest') : status === 'processing' ? t('Processing') : t('Failed')
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 font-mono text-[11px] tracking-wide uppercase',
        s.text,
      )}
    >
      <span aria-hidden="true" className={clsx('size-1.5 shrink-0', s.mark)} />
      {label}
    </span>
  )
}

/* ------------------------------ Lead controls ------------------------------ */

/**
 * The disclosure control: a triangle before the label that turns to point
 * down while the row's brief is open, faint at rest so a column of them does
 * not shout, darker when the row is hovered. It is positioned, so it sits
 * above the row link: a press unfolds the brief and stays on the page.
 */
export function ExpandButton({
  open,
  panelId,
  onToggle,
}: {
  open: boolean
  panelId: string
  onToggle: () => void
}) {
  const t = useT()
  const label = open ? t('Hide brief') : t('Show brief')
  return (
    <button
      type="button"
      aria-expanded={open}
      aria-controls={open ? panelId : undefined}
      aria-label={label}
      title={label}
      onClick={onToggle}
      className={clsx(
        'relative inline-flex size-7 items-center justify-center rounded-sm transition-colors duration-150 ease-out',
        'text-zinc-300 group-hover:text-zinc-500 hover:text-zinc-950! dark:text-zinc-600 dark:group-hover:text-zinc-400 dark:hover:text-white!',
        // No hover on touch: the triangle must be seen to be pressed.
        'pointer-coarse:text-zinc-500 dark:pointer-coarse:text-zinc-400',
        open && 'text-zinc-700 dark:text-zinc-200',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500',
      )}
    >
      <ChevronRightIcon
        aria-hidden="true"
        strokeWidth={1.75}
        className={clsx(
          'size-4 transition-transform duration-200 ease-out motion-reduce:transition-none',
          open && 'rotate-90',
        )}
      />
    </button>
  )
}

/** A lead control's footprint, so a row (or a bone) without one keeps the loaded height. */
export function LeadSlot() {
  return <span aria-hidden="true" className="flex size-7" />
}

/** A lead column's heading: read out, not shown — the control names itself. */
export function LeadHeading({ children }: { children: ReactNode }) {
  return <span className="sr-only">{children}</span>
}

/* ------------------------------- Brief panel ------------------------------- */

/**
 * What a completed row discloses: the funnel line, the brief in serif, the
 * link into the briefing, and its strongest papers. Home's ledger and the
 * Briefings archive open the same panel.
 */
export function BriefPanel({ brief }: { brief: HomeBrief }) {
  const t = useT()
  return (
    <div
      className={clsx(
        'grid gap-6 pl-3 whitespace-normal',
        // Nothing to list beside the brief: let it run at its own
        // measure rather than pairing it with an empty column.
        brief.top.length > 0 && 'lg:grid-cols-5',
      )}
    >
      <div className={clsx(brief.top.length > 0 && 'lg:col-span-3')}>
        <p className="font-mono text-[11px] text-zinc-500 tabular-nums dark:text-zinc-400">
          {fmt(t('{screened} screened → {included} included'), {
            screened: brief.screened,
            included: brief.included,
          })}
        </p>
        <AnswerMarkdown
          text={brief.inBrief}
          className="mt-2 max-w-xl font-serif text-[15px]/6 text-pretty text-zinc-700 dark:text-zinc-200"
        />
        <TextLink href={brief.href} className="mt-2 inline-block">
          {t('Open briefing →')}
        </TextLink>
      </div>
      {brief.top.length > 0 && (
        <div className="lg:col-span-2">
          <TopPapers papers={brief.top} dense />
        </div>
      )}
    </div>
  )
}

/* --------------------------------- Rows --------------------------------- */

function Row({
  row,
  open,
  onToggle,
  onRetry,
  busy,
  stars,
}: {
  row: HomeRow
  open: boolean
  onToggle: () => void
  onRetry: () => void
  busy: boolean
  stars: boolean
}) {
  const t = useT()
  const panelId = `briefing-${row.id}`
  const current = row.status === 'current'
  const { brief } = row
  return (
    <>
      {/* `href` makes the row a link — the table lays one over every cell —
          and `group` lets the triangle and star react to the row's hover. The
          two controls are positioned, so they paint above the link. A row
          still processing or failed has no href: nothing to open, no hover. */}
      <TableRow
        data-row="briefing"
        href={brief?.href}
        title={brief ? rowTitle(row, t) : undefined}
        className={clsx('group', current && 'bg-foreground/3')}
      >
        <TableCell className={COL.expand.cell}>
          {brief ? (
            <span className="flex">
              <ExpandButton open={open} panelId={panelId} onToggle={onToggle} />
            </span>
          ) : (
            <LeadSlot />
          )}
        </TableCell>
        {stars && (
          <TableCell className={COL.star.cell}>
            {brief ? (
              <span className="relative flex">
                <StarButton kind="briefing" id={row.id} />
              </span>
            ) : (
              <LeadSlot />
            )}
          </TableCell>
        )}
        <TableCell className={COL.domain.cell}>
          <span className="flex items-center gap-2.5">
            <span
              aria-hidden="true"
              className={clsx('h-4 w-0.5 shrink-0', current ? 'bg-accent' : 'bg-transparent')}
            />
            {row.domain}
          </span>
        </TableCell>
        <TableCell className={COL.period.cell}>{row.period}</TableCell>
        <TableCell className={COL.generated.cell}>
          {row.generated ? (
            <Generated day={row.generated} stamp={row.stamp ?? null} />
          ) : row.failedDay !== null ? (
            fmt(t('failed {date}'), { date: row.failedDay })
          ) : (
            fmt(t('started {time} UTC'), { time: row.startedClock ?? '—' })
          )}
        </TableCell>
        <TableCell className={COL.papers.cell}>
          {row.papers ?? <span className="text-zinc-400">—</span>}
        </TableCell>
        <TableCell className={COL.status.cell}>
          <span className="flex items-center justify-end gap-3">
            <StatusLabel status={row.status} />
            {row.retry && (
              // Positioned like the triangle and the star: should a linked
              // row ever carry Retry, the button still takes the click.
              <button
                type="button"
                onClick={onRetry}
                disabled={busy}
                className="relative rounded-sm border border-line px-2 py-0.5 text-xs font-medium text-zinc-700 transition-colors hover:border-zinc-400 hover:text-zinc-950 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 disabled:opacity-50 dark:text-zinc-200 dark:hover:text-white"
              >
                {t('Retry')}
              </button>
            )}
          </span>
        </TableCell>
      </TableRow>

      {open && brief && (
        <TableRow data-row="brief" id={panelId} className={clsx(current && 'bg-foreground/3')}>
          {/* The row above keeps its own bottom padding; the panel adds a
              little of its own so its first line is not against the rule. */}
          <TableCell colSpan={columnsFor(stars).length} className="pt-3! pb-5!">
            <BriefPanel brief={brief} />
          </TableCell>
        </TableRow>
      )}
    </>
  )
}

/** A 409 from the start route: the page is stale, another run is in flight. */
export function isConflict(error: unknown): boolean {
  return (
    !!error &&
    typeof error === 'object' &&
    'problem' in error &&
    (error as { problem: { status?: number } }).problem.status === 409
  )
}

/* -------------------------------- Ledger -------------------------------- */

export function Ledger({ rows, busy }: { rows: HomeRow[]; busy: boolean }) {
  const t = useT()
  const router = useRouter()
  const { stars } = useFeatures()
  const [openId, setOpenId] = useState<string | null>(null)
  const [retrying, setRetrying] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pending, startTransition] = useTransition()

  async function retry(row: HomeRow) {
    if (!row.retry) return
    setRetrying(true)
    setError(null)
    try {
      await bffFetch('/bff/pipeline-runs/start', {
        method: 'POST',
        body: JSON.stringify(row.retry),
      })
      // The new run is in Django's list before the response lands: re-read.
      startTransition(() => router.refresh())
    } catch (err) {
      console.error('[home] retry failed', err)
      setError(errorsFromSubmit(err, [], t, t("Couldn't start the run. Try again."))._)
      // 409: another run is already in flight — show it.
      if (isConflict(err)) startTransition(() => router.refresh())
    } finally {
      setRetrying(false)
    }
  }

  return (
    <div>
      <LedgerFrame
        state="loaded"
        stars={stars}
        rows={rows.map((row) => (
          <Row
            key={row.id}
            row={row}
            stars={stars}
            open={row.id === openId}
            onToggle={() => setOpenId((id) => (id === row.id ? null : row.id))}
            onRetry={() => void retry(row)}
            busy={busy || retrying || pending}
          />
        ))}
      />
      {error && (
        <p role="alert" className="mt-2 text-xs text-negative">
          {error}
        </p>
      )}
    </div>
  )
}

// Domain names of different lengths, so the skeleton reads as a list.
const DOMAIN_DIGITS = [16, 11, 14, 16, 11]

export function LedgerSkeleton({
  rows = 5,
  features = DEFAULT_FEATURES,
}: {
  rows?: number
  /** The page's flags, so the bones have the star column exactly when the rows will. */
  features?: Features
}) {
  const stars = features.stars
  return (
    <LedgerFrame
      state="skeleton"
      stars={stars}
      rows={Array.from({ length: rows }, (_, i) => (
        <TableRow key={i} data-row="briefing">
          <TableCell className={COL.expand.cell}>
            <LeadSlot />
          </TableCell>
          {stars && (
            <TableCell className={COL.star.cell}>
              <LeadSlot />
            </TableCell>
          )}
          <TableCell className={COL.domain.cell}>
            <span className="flex items-center gap-2.5">
              <span aria-hidden="true" className="h-4 w-0.5 shrink-0 bg-transparent" />
              <Bone.Number digits={DOMAIN_DIGITS[i % DOMAIN_DIGITS.length]} />
            </span>
          </TableCell>
          <TableCell className={COL.period.cell}>
            <Bone.Number digits={16} />
          </TableCell>
          <TableCell className={COL.generated.cell}>
            <Bone.Number digits={10} />
          </TableCell>
          <TableCell className={COL.papers.cell}>
            <Bone.Number digits={2} />
          </TableCell>
          <TableCell className={COL.status.cell}>
            {i === 0 && (
              <span className="font-mono text-[11px]">
                <Bone.Number digits={9} />
              </span>
            )}
          </TableCell>
        </TableRow>
      ))}
    />
  )
}

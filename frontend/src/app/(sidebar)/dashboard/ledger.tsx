'use client'

import { AnswerMarkdown } from '@/components/answer-markdown'
import { Bone } from '@/components/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/table'
import { bffFetch } from '@/lib/bff/client'
import type { StartRun } from '@/lib/bff/pipeline-runs/schema'
import { errorsFromSubmit } from '@/lib/bff/problem-copy'
import { fmt } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import clsx from 'clsx'
import { useRouter } from 'next/navigation'
import { useState, useTransition, type ReactNode } from 'react'
import { TextLink, TopPapers, type HomePaper } from './home-ui'

/**
 * Recent Briefings: the five newest runs across the user's domains, newest
 * first. A completed row is a disclosure — click it (or press Enter on the
 * domain) and its brief and top three papers open beneath the cells; one
 * row open at a time. The way into the briefing is the panel's link. A
 * failed row offers Retry, which resends the run's own parameters.
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
  /** "07:12" — when the run started (UTC), for a row still processing. */
  startedClock: string | null
  /** The day the run failed, already worded; null unless it failed. */
  failedDay: string | null
  /** Papers in the briefing; null while processing or after a failure. */
  papers: number | null
  /** What Retry resends — the failed run's own parameters. */
  retry: StartRun | null
  /** The disclosure content — present on completed rows whose edition exists. */
  brief: HomeBrief | null
}

// One entry per column: the classes of its header and body cells. Both the
// loaded table and its skeleton render from this list, so they cannot drift.
const COL = {
  domain: { head: '', cell: 'font-medium' },
  period: { head: '', cell: 'font-mono text-xs text-zinc-600 tabular-nums dark:text-zinc-300' },
  generated: {
    head: '',
    cell: 'font-mono text-xs text-zinc-500 tabular-nums dark:text-zinc-400',
  },
  papers: { head: 'text-right', cell: 'text-right font-mono tabular-nums' },
  status: { head: 'text-right', cell: 'text-right' },
} as const

const COLUMNS = ['domain', 'period', 'generated', 'papers', 'status'] as const

function LedgerFrame({ rows, state }: { rows: ReactNode; state: 'loaded' | 'skeleton' }) {
  const t = useT()
  const labels: Record<(typeof COLUMNS)[number], string> = {
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
          {COLUMNS.map((key) => (
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

/** Current · Processing · Failed; completed briefings that are not current carry none. */
function StatusLabel({ status }: { status: RowStatus }) {
  const t = useT()
  if (status === 'done') return null
  const s = STATUS_CLASS[status]
  const label =
    status === 'current' ? t('Current') : status === 'processing' ? t('Processing') : t('Failed')
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

/* --------------------------------- Rows --------------------------------- */

function Row({
  row,
  open,
  onToggle,
  onRetry,
  busy,
}: {
  row: HomeRow
  open: boolean
  onToggle: () => void
  onRetry: () => void
  busy: boolean
}) {
  const t = useT()
  const expandable = row.brief !== null
  const panelId = `briefing-${row.id}`
  const current = row.status === 'current'
  return (
    <>
      <TableRow
        data-row="briefing"
        onClick={expandable ? onToggle : undefined}
        className={clsx(
          current && 'bg-foreground/3',
          expandable && 'cursor-pointer hover:bg-zinc-950/2.5 dark:hover:bg-white/2.5',
        )}
      >
        <TableCell className={COL.domain.cell}>
          <span className="flex items-center gap-2.5">
            <span
              aria-hidden="true"
              className={clsx('h-4 w-0.5 shrink-0', current ? 'bg-accent' : 'bg-transparent')}
            />
            {expandable ? (
              // The keyboard handle: the row's click target is the whole row,
              // its accessible control is the domain name.
              <button
                type="button"
                aria-expanded={open}
                aria-controls={open ? panelId : undefined}
                onClick={(e) => {
                  e.stopPropagation()
                  onToggle()
                }}
                className="rounded-sm text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500"
              >
                {row.domain}
              </button>
            ) : (
              row.domain
            )}
          </span>
        </TableCell>
        <TableCell className={COL.period.cell}>{row.period}</TableCell>
        <TableCell className={COL.generated.cell}>
          {row.generated ??
            (row.failedDay !== null
              ? fmt(t('failed {date}'), { date: row.failedDay })
              : fmt(t('started {time} UTC'), { time: row.startedClock ?? '—' }))}
        </TableCell>
        <TableCell className={COL.papers.cell}>
          {row.papers ?? <span className="text-zinc-400">—</span>}
        </TableCell>
        <TableCell className={COL.status.cell}>
          <span className="flex items-center justify-end gap-3">
            <StatusLabel status={row.status} />
            {row.retry && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  onRetry()
                }}
                disabled={busy}
                className="rounded-sm border border-line px-2 py-0.5 text-xs font-medium text-zinc-700 transition-colors hover:border-zinc-400 hover:text-zinc-950 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 disabled:opacity-50 dark:text-zinc-200 dark:hover:text-white"
              >
                {t('Retry')}
              </button>
            )}
          </span>
        </TableCell>
      </TableRow>

      {open && row.brief && (
        <TableRow data-row="brief" id={panelId} className={clsx(current && 'bg-foreground/3')}>
          {/* The row above keeps its own bottom padding; the panel adds a
              little of its own so its first line is not against the rule. */}
          <TableCell colSpan={COLUMNS.length} className="pt-3! pb-5!">
            <div
              className={clsx(
                'grid gap-6 pl-3 whitespace-normal',
                // Nothing to list beside the brief: let it run at its own
                // measure rather than pairing it with an empty column.
                row.brief.top.length > 0 && 'lg:grid-cols-5',
              )}
            >
              <div className={clsx(row.brief.top.length > 0 && 'lg:col-span-3')}>
                <p className="font-mono text-[11px] text-zinc-500 tabular-nums dark:text-zinc-400">
                  {fmt(t('{screened} screened → {included} included'), {
                    screened: row.brief.screened,
                    included: row.brief.included,
                  })}
                </p>
                <AnswerMarkdown
                  text={row.brief.inBrief}
                  className="mt-2 max-w-xl font-serif text-[15px]/6 text-pretty text-zinc-700 dark:text-zinc-200"
                />
                <TextLink href={row.brief.href} className="mt-2 inline-block">
                  {t('Open briefing →')}
                </TextLink>
              </div>
              {row.brief.top.length > 0 && (
                <div className="lg:col-span-2">
                  <TopPapers papers={row.brief.top} dense />
                </div>
              )}
            </div>
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
        rows={rows.map((row) => (
          <Row
            key={row.id}
            row={row}
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

export function LedgerSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <LedgerFrame
      state="skeleton"
      rows={Array.from({ length: rows }, (_, i) => (
        <TableRow key={i} data-row="briefing">
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

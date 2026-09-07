'use client'

import { PageNav } from '@/components/page-nav'
import { Bone } from '@/components/skeleton'
import { StarButton, StarredChip } from '@/components/star'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/table'
import { useT } from '@/lib/i18n-client'
import { useStars } from '@/lib/stars-client'
import clsx from 'clsx'
import { useMemo, useState, type ReactNode } from 'react'
import { BriefPanel, StatusLabel } from '../dashboard/ledger'
import { filterRows, paginate, searchOf, type ArchiveRow, type ArchiveState } from './rows'

/**
 * The Briefings archive: every completed briefing across the user's domains
 * as a ledger, newest first — Home's Recent Briefings, continued. Domain
 * chips and the Starred filter above, twenty rows a page below. A row is a
 * disclosure: click it (or press Enter on the domain) and its brief and top
 * papers open beneath the cells, one at a time; the way into the briefing is
 * the panel's link. Filter and page live in the URL, so Back restores them.
 */

// One entry per column: the classes of its header and body cells. Both the
// loaded ledger and its skeleton render from this list, so they cannot drift.
const COL = {
  star: { head: 'w-7 pr-0!', cell: 'w-7 pr-0!' },
  domain: { head: '', cell: 'font-medium' },
  period: { head: '', cell: 'font-mono text-xs text-zinc-600 tabular-nums dark:text-zinc-300' },
  generated: {
    head: '',
    cell: 'font-mono text-xs text-zinc-500 tabular-nums dark:text-zinc-400',
  },
  screened: { head: 'text-right', cell: 'text-right font-mono tabular-nums' },
  included: { head: 'text-right', cell: 'text-right font-mono tabular-nums' },
  status: { head: 'text-right', cell: 'text-right' },
} as const

const COLUMNS = ['star', 'domain', 'period', 'generated', 'screened', 'included', 'status'] as const

/* -------------------------------- Frames -------------------------------- */

const CHIP =
  'inline-flex h-6 items-center rounded-full border bg-white px-2.5 text-xs transition-colors duration-150 ease-out dark:bg-zinc-900'
const CHIP_ON = 'border-zinc-950 text-zinc-950 dark:border-white dark:text-white'
const CHIP_OFF =
  'border-zinc-950/10 text-zinc-600 hover:border-zinc-400 dark:border-white/10 dark:text-zinc-300 dark:hover:border-zinc-500'

function LedgerFrame({
  state,
  domains,
  starred,
  rows,
  empty,
  nav,
}: {
  state: 'loaded' | 'skeleton'
  /** The domain chips, or null when there is only one domain to show. */
  domains: ReactNode
  starred: ReactNode
  rows: ReactNode
  empty?: ReactNode
  nav?: ReactNode
}) {
  const t = useT()
  const labels: Record<(typeof COLUMNS)[number], string> = {
    star: '',
    domain: t('Domain'),
    period: t('Period'),
    generated: t('Generated'),
    screened: t('Screened'),
    included: t('Included'),
    status: '',
  }
  return (
    <div data-shape="briefing-ledger" data-state={state} className="space-y-4">
      <div data-row="filters" className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">{domains}</div>
        {starred}
      </div>
      <Table dense>
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
      {empty}
      {nav}
    </div>
  )
}

/* --------------------------------- Rows --------------------------------- */

function Row({ row, open, onToggle }: { row: ArchiveRow; open: boolean; onToggle: () => void }) {
  const panelId = `briefing-${row.id}`
  return (
    <>
      {/* `group` on the row: the star in the first cell shows on hover. */}
      <TableRow
        data-row="briefing"
        onClick={onToggle}
        className={clsx(
          'group cursor-pointer hover:bg-zinc-950/2.5 dark:hover:bg-white/2.5',
          row.current && 'bg-foreground/3',
        )}
      >
        <TableCell className={COL.star.cell}>
          <span className="flex">
            <StarButton kind="briefing" id={row.id} />
          </span>
        </TableCell>
        <TableCell className={COL.domain.cell}>
          <span className="flex items-center gap-2.5">
            <span
              aria-hidden="true"
              className={clsx('h-4 w-0.5 shrink-0', row.current ? 'bg-accent' : 'bg-transparent')}
            />
            {/* The keyboard handle: the row's click target is the whole row,
                its accessible control is the domain name. */}
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
          </span>
        </TableCell>
        <TableCell className={COL.period.cell}>{row.period}</TableCell>
        <TableCell className={COL.generated.cell}>{row.generated}</TableCell>
        <TableCell className={COL.screened.cell}>{row.screened}</TableCell>
        <TableCell className={COL.included.cell}>{row.included}</TableCell>
        <TableCell className={COL.status.cell}>
          <StatusLabel status={row.current ? 'current' : 'done'} />
        </TableCell>
      </TableRow>

      {open && (
        <TableRow data-row="brief" id={panelId} className={clsx(row.current && 'bg-foreground/3')}>
          <TableCell colSpan={COLUMNS.length} className="pt-0! pb-5!">
            <BriefPanel brief={row.brief} />
          </TableCell>
        </TableRow>
      )}
    </>
  )
}

/* -------------------------------- Ledger -------------------------------- */

export function BriefingLedger({
  rows,
  domains,
  initial,
  syncUrl = true,
}: {
  /** Every completed briefing, newest first. */
  rows: ArchiveRow[]
  /** The user's domains; the chips show only when there is more than one. */
  domains: { id: string; name: string }[]
  /** From the URL; the ledger owns the state from here on. */
  initial: ArchiveState
  /** Mirror filter and page into the URL (off in the gallery). */
  syncUrl?: boolean
}) {
  const t = useT()
  const { isStarred } = useStars()
  const [state, setState] = useState<ArchiveState>(initial)
  const [openId, setOpenId] = useState<string | null>(null)

  const starredIds = useMemo(
    () => new Set(rows.filter((row) => isStarred('briefing', row.id)).map((row) => row.id)),
    [rows, isStarred],
  )
  const filtered = filterRows(rows, state, starredIds)
  const { items, page, pageCount } = paginate(filtered, state.page)

  function update(patch: Partial<ArchiveState>) {
    const next = { ...state, ...patch }
    // A narrower or wider list starts again from its first page.
    if ('domain' in patch || 'starred' in patch) next.page = 1
    setState(next)
    // No navigation, no refetch: the App Router picks the query up from
    // history, and the server reads it again on the next real visit.
    if (syncUrl) window.history.replaceState(null, '', window.location.pathname + searchOf(next))
  }

  const emptyCopy =
    state.starred && starredIds.size === 0
      ? t('Nothing starred yet.')
      : t('No briefings for this domain yet.')

  return (
    <LedgerFrame
      state="loaded"
      domains={
        domains.length > 1 && (
          <div role="group" aria-label={t('Filter by domain')} className="contents">
            {[{ id: null, name: t('All') }, ...domains].map((d) => (
              <button
                key={d.id ?? 'all'}
                type="button"
                aria-pressed={state.domain === d.id}
                onClick={() => update({ domain: d.id })}
                className={clsx(CHIP, state.domain === d.id ? CHIP_ON : CHIP_OFF)}
              >
                {d.name}
              </button>
            ))}
          </div>
        )
      }
      starred={
        <StarredChip
          active={state.starred}
          count={starredIds.size}
          onToggle={() => update({ starred: !state.starred })}
          className="ml-auto"
        />
      }
      rows={items.map((row) => (
        <Row
          key={row.id}
          row={row}
          open={row.id === openId}
          onToggle={() => setOpenId((id) => (id === row.id ? null : row.id))}
        />
      ))}
      empty={
        filtered.length === 0 && (
          <div className="border-line rounded-sm border border-dashed p-10 text-center text-sm text-zinc-400 dark:text-zinc-500">
            {emptyCopy}
          </div>
        )
      }
      nav={
        <PageNav
          page={page}
          pageCount={pageCount}
          onChange={(p) => update({ page: p })}
          className="mt-6"
          labels={{ prev: t('Previous'), next: t('Next') }}
        />
      }
    />
  )
}

/* -------------------------------- Skeleton ------------------------------- */

// Domain names of different lengths, so the skeleton reads as a list.
const DOMAIN_DIGITS = [16, 11, 14, 16, 11]

/**
 * The ledger's bones. `domains` is the chip row: null when the shell does not
 * know them yet (loading.tsx), the names when the page does — so the row is
 * the same height in both states.
 */
export function BriefingLedgerSkeleton({
  rows = 10,
  domains,
}: {
  rows?: number
  domains: string[] | null
}) {
  const t = useT()
  return (
    <LedgerFrame
      state="skeleton"
      domains={
        domains === null ? (
          <>
            <Bone.Chip width={40} className="h-6!" />
            <Bone.Chip width={112} className="h-6!" />
            <Bone.Chip width={88} className="h-6!" />
          </>
        ) : (
          domains.length > 1 &&
          [t('All'), ...domains].map((name, i) => (
            <span key={i} className={clsx(CHIP, i === 0 ? CHIP_ON : CHIP_OFF)}>
              {name}
            </span>
          ))
        )
      }
      starred={<Bone.Chip width={82} className="ml-auto h-6!" />}
      rows={Array.from({ length: rows }, (_, i) => (
        <TableRow key={i} data-row="briefing" className={clsx(i === 0 && 'bg-foreground/3')}>
          <TableCell className={COL.star.cell}>
            {/* The star's footprint, so the row keeps its loaded height. */}
            <span aria-hidden="true" className="flex size-7" />
          </TableCell>
          <TableCell className={COL.domain.cell}>
            <span className="flex items-center gap-2.5">
              <span
                aria-hidden="true"
                className={clsx('h-4 w-0.5 shrink-0', i === 0 ? 'bg-accent' : 'bg-transparent')}
              />
              <Bone.Number digits={DOMAIN_DIGITS[i % DOMAIN_DIGITS.length]} />
            </span>
          </TableCell>
          <TableCell className={COL.period.cell}>
            <Bone.Number digits={16} />
          </TableCell>
          <TableCell className={COL.generated.cell}>
            <Bone.Number digits={10} />
          </TableCell>
          <TableCell className={COL.screened.cell}>
            <Bone.Number digits={3} />
          </TableCell>
          <TableCell className={COL.included.cell}>
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

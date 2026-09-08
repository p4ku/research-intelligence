'use client'

import { PageNav } from '@/components/page-nav'
import { Bone } from '@/components/skeleton'
import { StarButton, StarredChip } from '@/components/star'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/table'
import { ALL_ON, type Features } from '@/lib/features'
import { useFeatures } from '@/lib/features-client'
import { useT } from '@/lib/i18n-client'
import { useStars } from '@/lib/stars-client'
import clsx from 'clsx'
import { useSearchParams } from 'next/navigation'
import { useMemo, useState, type ReactNode } from 'react'
import { BriefPanel, ExpandButton, LEAD, LeadSlot, StatusLabel } from '../dashboard/ledger'
import {
  filterRows,
  paginate,
  searchOf,
  stateFrom,
  type ArchiveRow,
  type ArchiveState,
} from './rows'

/**
 * The Briefings archive: every completed briefing across the user's domains
 * as a ledger, newest first — Home's Recent Briefings, continued. Domain
 * chips and the Starred filter above, twenty rows a page below. A row is a
 * link: click it anywhere and the briefing opens. The disclosure triangle at
 * its start is the other path — press it and the brief and top papers unfold
 * beneath the cells, one row at a time, without leaving the page. A right
 * chevron at the row's end would promise navigation, which is the row's own
 * job; a triangle before the label is the file-tree convention for "unfold".
 * The triangle and the star both sit above the row link, so neither click
 * navigates. Home's Recent Briefings is the same row, and shares the parts.
 * Filter and page live in the URL — the ledger reads them from it on every
 * render — so Back and Forward show what the address says.
 */

// One entry per column: the classes of its header and body cells. Both the
// loaded ledger and its skeleton render from this list, so they cannot drift.
const COL = {
  expand: LEAD.expand,
  star: LEAD.star,
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

const COLUMNS = [
  'expand',
  'star',
  'domain',
  'period',
  'generated',
  'screened',
  'included',
  'status',
] as const

/**
 * The columns this render has. With `stars` off the star column leaves the
 * list entirely rather than rendering an empty cell: header, body cells,
 * skeleton footprint and the expanded brief's colSpan all follow from here,
 * so a hidden star cannot leave a 28px gutter down every row.
 */
function columnsFor(stars: boolean): readonly (typeof COLUMNS)[number][] {
  return stars ? COLUMNS : COLUMNS.filter((key) => key !== 'star')
}

/* -------------------------------- Frames -------------------------------- */

const CHIP =
  'inline-flex h-6 items-center rounded-full border bg-white px-2.5 text-xs transition-colors duration-150 ease-out dark:bg-zinc-900'
const CHIP_ON = 'border-zinc-950 text-zinc-950 dark:border-white dark:text-white'
const CHIP_OFF =
  'border-zinc-950/10 text-zinc-600 hover:border-zinc-400 dark:border-white/10 dark:text-zinc-300 dark:hover:border-zinc-500'

function LedgerFrame({
  state,
  stars,
  domains,
  starred,
  rows,
  empty,
  nav,
}: {
  state: 'loaded' | 'skeleton'
  /** Whether this render has the star column — one source per tree, never the context twice. */
  stars: boolean
  /** The domain chips, or null when there is only one domain to show. */
  domains: ReactNode
  starred: ReactNode
  rows: ReactNode
  empty?: ReactNode
  nav?: ReactNode
}) {
  const t = useT()
  const columns = columnsFor(stars)
  const labels: Record<(typeof COLUMNS)[number], string> = {
    star: '',
    domain: t('Domain'),
    period: t('Period'),
    generated: t('Generated'),
    screened: t('Screened'),
    included: t('Included'),
    status: '',
    expand: '',
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
            {columns.map((key) => (
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

function Row({
  row,
  open,
  onToggle,
  stars,
}: {
  row: ArchiveRow
  open: boolean
  onToggle: () => void
  stars: boolean
}) {
  const t = useT()
  const panelId = `briefing-${row.id}`
  return (
    <>
      {/* `href` makes the row a link — the table lays one over every cell —
          and `group` lets the triangle and star react to the row's hover. The
          two controls are positioned, so they paint above the link. */}
      <TableRow
        data-row="briefing"
        href={row.brief.href}
        title={`${t('Open briefing')}: ${row.domain}, ${row.period}`}
        className={clsx('group', row.current && 'bg-foreground/3')}
      >
        <TableCell className={COL.expand.cell}>
          <span className="flex">
            <ExpandButton open={open} panelId={panelId} onToggle={onToggle} />
          </span>
        </TableCell>
        {stars && (
          <TableCell className={COL.star.cell}>
            <span className="relative flex">
              <StarButton kind="briefing" id={row.id} />
            </span>
          </TableCell>
        )}
        <TableCell className={COL.domain.cell}>
          <span className="flex items-center gap-2.5">
            <span
              aria-hidden="true"
              className={clsx('h-4 w-0.5 shrink-0', row.current ? 'bg-accent' : 'bg-transparent')}
            />
            {row.domain}
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
          <TableCell colSpan={columnsFor(stars).length} className="pt-3! pb-5!">
            <BriefPanel brief={row.brief} />
          </TableCell>
        </TableRow>
      )}
    </>
  )
}

/* -------------------------------- Ledger -------------------------------- */

const DEFAULT_STATE: ArchiveState = { domain: null, starred: false, page: 1 }

export function BriefingLedger({
  rows,
  domains,
  syncUrl = true,
}: {
  /** Every completed briefing, newest first. */
  rows: ArchiveRow[]
  /** The user's domains; the chips show only when there is more than one. */
  domains: { id: string; name: string }[]
  /** Keep filter and page in the URL (off in the gallery, which holds them locally). */
  syncUrl?: boolean
}) {
  const t = useT()
  const { isStarred } = useStars()
  const { stars } = useFeatures()
  // The URL is the state. The App Router updates useSearchParams on the
  // replaceState below and on Back/Forward, and a traversal restores the
  // page from its cache without a server render — so nothing is seeded
  // from a prop that could go stale.
  const params = useSearchParams()
  const [local, setLocal] = useState<ArchiveState>(DEFAULT_STATE)
  const urlState = syncUrl ? stateFrom(Object.fromEntries(params), domains) : local
  // The effective Starred filter, not the state: `?starred=1` lives in the URL
  // and this component does not own the address bar, so it survives a flip and
  // a reload alike — forcing the derived value is what makes a reload with the
  // flag off show the full ledger instead of a list nothing can widen again.
  const state: ArchiveState = { ...urlState, starred: stars && urlState.starred }
  const [openId, setOpenId] = useState<string | null>(null)

  const starredIds = useMemo(
    () => new Set(rows.filter((row) => isStarred('briefing', row.id)).map((row) => row.id)),
    [rows, isStarred],
  )
  const filtered = filterRows(rows, state, starredIds)
  const { items, page, pageCount } = paginate(filtered, state.page)

  function update(patch: Partial<ArchiveState>) {
    // From `urlState`, not the forced `state`: only the rendered value is
    // forced, and a domain or pager click must not quietly rewrite the address
    // bar without a `?starred=1` the user never cleared. Identical while stars
    // are on, and with them off it is what keeps the flip non-destructive.
    const next = { ...urlState, ...patch }
    // A narrower or wider list starts again from its first page.
    if ('domain' in patch || 'starred' in patch) next.page = 1
    // No navigation, no refetch: the App Router picks the query up from
    // history, and the server reads it again on the next real visit.
    if (syncUrl) window.history.replaceState(null, '', window.location.pathname + searchOf(next))
    else setLocal(next)
  }

  const emptyCopy = !state.starred
    ? t('No briefings for this domain yet.')
    : starredIds.size === 0
      ? t('Nothing starred yet.')
      : t('Nothing starred in this domain.')

  return (
    <LedgerFrame
      state="loaded"
      stars={stars}
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
        stars && (
          <StarredChip
            active={state.starred}
            count={starredIds.size}
            onToggle={() => update({ starred: !state.starred })}
            className="ml-auto"
          />
        )
      }
      rows={items.map((row) => (
        <Row
          key={row.id}
          row={row}
          stars={stars}
          open={row.id === openId}
          onToggle={() => setOpenId((id) => (id === row.id ? null : row.id))}
        />
      ))}
      empty={
        filtered.length === 0 && (
          <div className="rounded-sm border border-dashed border-line p-10 text-center text-sm text-zinc-400 dark:text-zinc-500">
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
  features = ALL_ON,
}: {
  rows?: number
  domains: string[] | null
  /** Optional: the Studio gallery renders this skeleton directly, all-on. */
  features?: Features
}) {
  const t = useT()
  return (
    <LedgerFrame
      state="skeleton"
      stars={features.stars}
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
      starred={features.stars && <Bone.Chip width={82} className="ml-auto h-6!" />}
      rows={Array.from({ length: rows }, (_, i) => (
        <TableRow key={i} data-row="briefing" className={clsx(i === 0 && 'bg-foreground/3')}>
          <TableCell className={COL.expand.cell}>
            <LeadSlot />
          </TableCell>
          {features.stars && (
            <TableCell className={COL.star.cell}>
              <LeadSlot />
            </TableCell>
          )}
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

'use client'

/**
 * The middle pane: the scope's head (name, budget), the status filters,
 * "Needs attention" (runs plus workspace notices), then completed and
 * queued runs by day. Rows are RunRow buttons; row refs are collected so
 * the pane can hand focus back on close.
 */
import { Link } from '@/components/link'
import { Bone } from '@/components/skeleton'
import type { PipelineRun, RunStatus } from '@/lib/bff/pipeline-runs/schema'
import type { WorkspaceSummary } from '@/lib/bff/workspaces/schema'
import clsx from 'clsx'
import { useState } from 'react'
import { formatTokens, formatUsd } from '../run-presentation'
import {
  attentionRuns,
  fmtDay,
  groupByDay,
  isAttention,
  plural,
  STATUS_ORDER,
  statusCounts,
  type Filter,
  type Notice,
  type RunIndex,
  type WorkspaceSummaryDerived,
} from './derive'
import { EmptyWorkspaceCard } from './empty-workspace'
import { NoticeRow } from './notices'
import { Chip, FOCUS, Meter, MONO, Slab, STATUS_LABEL } from './primitives'
import { ROW_CLASS, RunRow } from './run-row'

/** Calm rows shown per scope before "Show all". Attention rows are never cut. */
export const CALM_ROWS = 60

const ROWS = 'border-line bg-surface overflow-hidden rounded-sm border shadow-xs'
const HEAD = 'border-line bg-surface border-b px-4 pt-3.5 pb-3'
const FILTER_BTN =
  'border-line bg-surface text-muted-foreground hover:bg-foreground/3 rounded-sm border px-2 py-0.5 text-[11.5px] transition-colors duration-150 aria-pressed:border-foreground aria-pressed:bg-foreground aria-pressed:text-background max-sm:min-h-11'

export interface RunListProps {
  scope: string
  workspace: WorkspaceSummary | null
  /** Runs in scope, newest first. */
  runs: PipelineRun[]
  index: RunIndex
  summary: WorkspaceSummaryDerived | null
  notices: Notice[]
  workspaceCount: number
  filter: Filter
  runId: string | null
  now: string
  truncated: boolean
  onFilter: (filter: Filter) => void
  onOpen: (id: string) => void
  onScope: (id: string) => void
  rowRef: (id: string, el: HTMLButtonElement | null) => void
}

export function RunList({
  scope,
  workspace: ws,
  runs,
  index,
  summary,
  notices,
  workspaceCount,
  filter,
  runId,
  now,
  truncated,
  onFilter,
  onOpen,
  onScope,
  rowRef,
}: RunListProps) {
  const [expandedScope, setExpandedScope] = useState<string | null>(null)
  const expanded = expandedScope === scope
  const showWorkspace = scope === 'all'
  const counts = statusCounts(runs)
  const present = STATUS_ORDER.filter((st) => counts[st])
  if (filter !== 'all' && !present.includes(filter)) present.push(filter)

  const row = (run: PipelineRun) => (
    <RunRow
      key={run.id}
      ref={(el) => rowRef(run.id, el)}
      run={run}
      index={index}
      showWorkspace={showWorkspace}
      open={runId === run.id}
      now={now}
      onOpen={onOpen}
    />
  )

  const dayGroups = (rows: PipelineRun[], label: string) => {
    const shown = expanded ? rows : rows.slice(0, CALM_ROWS)
    return (
      <section className="mt-5 first:mt-0">
        <Slab count={rows.length} className="mb-2.5">
          {label}
        </Slab>
        {groupByDay(shown).map((g) => (
          <section key={g.date} className="mb-4 last:mb-1">
            <div className="flex items-baseline justify-between gap-2.5 px-px pb-1.5">
              <h4 className={clsx(MONO, 'text-[11.5px] font-medium')}>{fmtDay(g.date)}</h4>
              <span className={clsx(MONO, 'text-muted-foreground text-[11px]')}>
                {g.runs.length} {plural(g.runs.length, 'run')}
              </span>
            </div>
            <div className={ROWS}>{g.runs.map(row)}</div>
          </section>
        ))}
        {rows.length > shown.length && (
          <button
            type="button"
            onClick={() => setExpandedScope(scope)}
            className={clsx(FILTER_BTN, FOCUS, 'mt-1')}
          >
            Show all <span className={MONO}>{rows.length}</span> runs
          </button>
        )}
      </section>
    )
  }

  return (
    <div data-shape="run-list">
      {/* ------------------------------- head ------------------------------- */}
      <div className={HEAD}>
        <h2 className="text-base leading-tight font-semibold break-words">
          {ws ? ws.name : 'All workspaces'}
        </h2>
        <div className="text-muted-foreground mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11.5px]">
          {ws ? (
            <>
              {ws.user_role && <Chip tone="plain">{ws.user_role}</Chip>}
              {ws.screening_llm_model && <Chip tone="plain">{ws.screening_llm_model}</Chip>}
              <span>
                <span className={MONO}>{ws.definitions.length}</span>{' '}
                {plural(ws.definitions.length, 'definition')} ·{' '}
                <span className={MONO}>{ws.scrapers.filter((s) => s.is_active).length}</span> active{' '}
                {plural(ws.scrapers.filter((s) => s.is_active).length, 'scraper')}
              </span>
            </>
          ) : (
            <span>
              <span className={MONO}>{workspaceCount}</span> {plural(workspaceCount, 'workspace')} ·{' '}
              <span className={MONO}>{runs.length}</span> {plural(runs.length, 'run')} · cost of
              listed runs{' '}
              <span className={MONO}>
                {formatUsd(runs.reduce((sum, r) => sum + r.usd_cost, 0))}
              </span>
            </span>
          )}
        </div>
        {ws && summary && (
          <div className="mt-3 grid grid-cols-1 gap-x-4 gap-y-2.5 lg:grid-cols-2">
            <Budget
              label="USD budget used"
              used={formatUsd(ws.usd_spent)}
              limit={ws.monthly_usd_limit === null ? null : formatUsd(ws.monthly_usd_limit)}
              pct={summary.usdPct}
              left={
                ws.monthly_usd_limit === null
                  ? null
                  : `${formatUsd(ws.monthly_usd_limit - ws.usd_spent)} left`
              }
            />
            <Budget
              label="Tokens used"
              used={formatTokens(ws.tokens_consumed)}
              limit={ws.monthly_token_limit === null ? null : formatTokens(ws.monthly_token_limit)}
              pct={summary.tokPct}
              left={
                <>
                  cost of listed runs{' '}
                  <b className={clsx(MONO, 'font-medium')}>{formatUsd(summary.runCost)}</b>
                </>
              }
            />
          </div>
        )}
      </div>

      {/* ------------------------------ filters ----------------------------- */}
      {runs.length > 0 && (
        <div
          role="group"
          aria-label="Filter runs by status"
          className="border-line bg-surface flex flex-wrap gap-1.5 border-b px-4 py-2"
        >
          <FilterButton active={filter === 'all'} onClick={() => onFilter('all')}>
            All <span className={MONO}>{runs.length}</span>
          </FilterButton>
          {present.map((st) => (
            <FilterButton key={st} active={filter === st} onClick={() => onFilter(st)}>
              {STATUS_LABEL[st]} <span className={MONO}>{counts[st] ?? 0}</span>
            </FilterButton>
          ))}
        </div>
      )}

      {/* ------------------------------- body ------------------------------- */}
      <div className="px-4 py-4">
        {ws && runs.length === 0 ? (
          <EmptyWorkspaceCard workspace={ws} />
        ) : (
          <>
            {!ws && runs.length === 0 && (
              <div className="border-line bg-surface mb-5 rounded-sm border px-4 py-4 shadow-xs">
                <h3 className="text-sm font-semibold">No runs in any workspace</h3>
                <p className="text-muted-foreground mt-1.5 max-w-[56ch] text-[12.5px]">
                  None of the <span className={MONO}>{workspaceCount}</span> workspaces has run yet.
                  Open a workspace from the rail or the notices below to see what it needs before
                  its first run.
                </p>
              </div>
            )}
            {filter === 'all' ? (
              <Unfiltered
                runs={runs}
                notices={notices}
                row={row}
                dayGroups={dayGroups}
                onScope={onScope}
              />
            ) : (
              <Filtered
                runs={runs.filter((r) => r.status === filter)}
                filter={filter}
                scopeName={ws ? ws.name : 'All workspaces'}
                dayGroups={dayGroups}
                onFilter={onFilter}
              />
            )}
          </>
        )}
        {truncated && (
          <p className="text-muted-foreground mt-5 text-xs">
            Showing the newest <span className={MONO}>500</span> runs across workspaces. Older runs
            are on the per-workspace{' '}
            <Link href="/studio/runs" className="text-accent-ink underline underline-offset-2">
              Runs
            </Link>{' '}
            page.
          </p>
        )}
      </div>
    </div>
  )
}

function Unfiltered({
  runs,
  notices,
  row,
  dayGroups,
  onScope,
}: {
  runs: PipelineRun[]
  notices: Notice[]
  row: (run: PipelineRun) => React.ReactNode
  dayGroups: (rows: PipelineRun[], label: string) => React.ReactNode
  onScope: (id: string) => void
}) {
  const attention = attentionRuns(runs)
  const calm = runs.filter((r) => !isAttention(r.status))
  const hasPending = calm.some((r) => r.status === 'pending')
  return (
    <>
      {(attention.length > 0 || notices.length > 0) && (
        <section className="mb-5">
          <Slab count={attention.length + notices.length} className="mb-2.5">
            Needs attention
          </Slab>
          {attention.length > 0 && <div className={ROWS}>{attention.map(row)}</div>}
          {notices.length > 0 && (
            <div className={clsx(ROWS, attention.length > 0 && 'mt-2')}>
              {notices.map((n) => (
                <NoticeRow key={`${n.kind}-${n.workspace.id}`} notice={n} onScope={onScope} />
              ))}
            </div>
          )}
        </section>
      )}
      {calm.length > 0 &&
        dayGroups(calm, hasPending ? 'Completed and queued runs' : 'Completed runs')}
    </>
  )
}

function Filtered({
  runs,
  filter,
  scopeName,
  dayGroups,
  onFilter,
}: {
  runs: PipelineRun[]
  filter: RunStatus
  scopeName: string
  dayGroups: (rows: PipelineRun[], label: string) => React.ReactNode
  onFilter: (filter: Filter) => void
}) {
  if (runs.length === 0) {
    return (
      <div className="border-line bg-surface rounded-sm border px-4 py-4 shadow-xs">
        <h3 className="text-sm font-semibold">No {STATUS_LABEL[filter].toLowerCase()} runs</h3>
        <p className="text-muted-foreground mt-1.5 text-[12.5px]">
          {scopeName} has no run with this status. The filter is still applied.
        </p>
        <button
          type="button"
          onClick={() => onFilter('all')}
          className={clsx(FILTER_BTN, FOCUS, 'mt-3')}
        >
          Show all runs
        </button>
      </div>
    )
  }
  return dayGroups(runs, `${STATUS_LABEL[filter]} runs`)
}

function FilterButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={clsx(FILTER_BTN, FOCUS)}
    >
      {children}
    </button>
  )
}

function Budget({
  label,
  used,
  limit,
  pct,
  left,
}: {
  label: string
  used: string
  limit: string | null
  pct: number | null
  left: React.ReactNode
}) {
  return (
    <div>
      <div className="text-muted-foreground mb-1 flex justify-between gap-2 text-[11px]">
        <span>{label}</span>
        <b className={clsx(MONO, 'text-foreground font-medium')}>
          {used}
          {limit !== null && <> of {limit}</>}
        </b>
      </div>
      {pct !== null ? <Meter percent={pct} /> : <span className="bg-line-soft block h-[3px]" />}
      <div className="text-muted-foreground mt-1 flex justify-between gap-2 text-[11px]">
        <span className={MONO}>{pct === null ? 'no limit set' : `${pct.toFixed(0)}% used`}</span>
        {left !== null && <span>{left}</span>}
      </div>
    </div>
  )
}

/** The list pane's bones: head, three filter chips, one day group of rows. */
export function RunListSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div data-shape="run-list" data-state="skeleton">
      <div className={HEAD}>
        <h2 className="text-base leading-tight font-semibold">
          <Bone.Text widths={['14ch']} />
        </h2>
        <div className="mt-1.5 text-[11.5px]">
          <Bone.Text widths={['40ch']} />
        </div>
      </div>
      {/* Filter chips keep the real button box so the strip is the same height. */}
      <div className="border-line bg-surface flex gap-1.5 border-b px-4 py-2">
        {['4ch', '8ch', '7ch'].map((w) => (
          <span key={w} className={FILTER_BTN}>
            <Bone.Text widths={[w]} />
          </span>
        ))}
      </div>
      <div className="px-4 py-4">
        <Slab as="div" count={<Bone.Number digits={2} />} className="mb-2.5">
          <Bone.Text widths={['12ch']} />
        </Slab>
        <section className="mb-4 last:mb-1">
          <div className="flex items-baseline justify-between px-px pb-1.5 text-[11.5px]">
            <Bone.Text widths={['14ch']} />
            <Bone.Text widths={['5ch']} />
          </div>
          <div className={ROWS}>
            {Array.from({ length: rows }, (_, i) => (
              <div key={i} data-row="run" className={ROW_CLASS}>
                <span className="flex items-baseline gap-2.5 text-[13px]">
                  <Bone.Number digits={5} className="text-xs" />
                  <span className="min-w-0 flex-1">
                    <Bone.Text widths={[i % 2 ? '18ch' : '24ch']} />
                    <Bone.Text widths={['20ch']} className="text-xs" />
                  </span>
                  <Bone.Chip width={80} className="ml-auto" />
                </span>
                <span className="mt-1.5 flex gap-3.5 text-xs">
                  <Bone.Text widths={['9ch']} />
                  <Bone.Text widths={['12ch']} />
                  <Bone.Text widths={['6ch']} />
                </span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}

import { Bone } from '@/components/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/table'
import { stageLabel, type PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import { fmt, formatNumber, localeOf, type Lang, type T } from '@/lib/i18n'
import type { ReactNode } from 'react'
import { formatDuration, formatUsd, RunStatus as RunStatusPill } from './run-presentation'
import { StopRunButton } from './stop-run-button'

/**
 * UTC, explicitly and labelled in the column header.
 *
 * These are server components: `toLocaleString` without a `timeZone` would use
 * the Node process's zone, which is the *server's*, not the reader's — a
 * Berlin operator would silently read Cloud Foundry's UTC as local time. The
 * backend stores and logs UTC, so showing UTC is also what correlates with the
 * logs an operator is cross-referencing. The *locale* follows the UI language;
 * the zone does not.
 */
function timestampUtc(iso: string | null, lang: Lang): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(localeOf(lang), {
    timeZone: 'UTC',
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

// One entry per column: the English header string (translated at render) and
// the classes of its header and body cells. Both the loaded table and its
// skeleton render from this list, so the columns cannot drift
// (scripts/skeleton-drift.ts measures each header). Exported because the
// headers reach t() dynamically: run-presentation.test.ts guards the German.
//
// Outcome reserves room for a Stop control beside the pill (stop-run-button.tsx),
// so a run settling from Running to Aborted — or the skeleton handing over to
// a table with a run in flight — moves no column. `min-w-48` is border-box:
// 160px of content after the cell's padding, against ~145px for the widest
// German pill ("Ausstehend") plus the control.
export const COLUMNS: { key: string; label: string; head?: string; cell?: string }[] = [
  { key: 'started', label: 'Started (UTC)', cell: 'font-medium tabular-nums' },
  { key: 'domain', label: 'Domain', cell: 'max-w-48 truncate text-zinc-500 dark:text-zinc-400' },
  { key: 'outcome', label: 'Outcome', head: 'min-w-48', cell: 'min-w-48' },
  { key: 'stage', label: 'Last stage', cell: 'text-zinc-500 dark:text-zinc-400' },
  { key: 'fetched', label: 'Fetched', head: 'text-right', cell: 'text-right tabular-nums' },
  { key: 'passed', label: 'Passed', head: 'text-right', cell: 'text-right tabular-nums' },
  {
    key: 'duration',
    label: 'Duration',
    head: 'text-right',
    cell: 'text-right text-zinc-500 tabular-nums dark:text-zinc-400',
  },
  {
    key: 'cost',
    label: 'Cost',
    head: 'text-right',
    cell: 'text-right text-zinc-500 tabular-nums dark:text-zinc-400',
  },
  { key: 'summary', label: 'Summary', cell: 'max-w-md truncate text-zinc-500 dark:text-zinc-400' },
]

interface RunRow {
  key: string
  /** Present on a loaded row; the skeleton's rows are not links. */
  href?: string
  title?: string
  /** One node per column, in COLUMNS order. */
  cells: ReactNode[]
}

/**
 * The table chrome shared by RunsTable and RunsTableSkeleton. Column widths
 * are content-derived (auto layout under whitespace-nowrap), so each header
 * carries data-row="col": the drift check then catches a skeleton whose bones
 * push a column wider or narrower than the real cells do.
 */
function RunsTableFrame({
  rows,
  state,
  t,
}: {
  rows: RunRow[]
  state: 'loaded' | 'skeleton'
  t: T
}) {
  return (
    <Table dense data-shape="runs-table" data-state={state}>
      <TableHead>
        <TableRow>
          {COLUMNS.map((column) => (
            <TableHeader key={column.key} data-row="col" className={column.head}>
              {t(column.label)}
            </TableHeader>
          ))}
        </TableRow>
      </TableHead>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.key} data-row="run" href={row.href} title={row.title}>
            {row.cells.map((cell, i) => (
              <TableCell key={COLUMNS[i].key} className={COLUMNS[i].cell}>
                {cell}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export function RunsTable({
  runs,
  stoppable,
  t = (s) => s,
  lang = 'en',
}: {
  runs: PipelineRun[]
  /** Workspace ids whose runs the reader may stop (admin or manager). */
  stoppable?: ReadonlySet<string>
  t?: T
  lang?: Lang
}) {
  const rows = runs.map(
    (run): RunRow => ({
      key: run.id,
      href: `/runs/${run.id}`,
      title: fmt(t('Run {id}'), { id: run.id }),
      cells: [
        timestampUtc(run.started_at, lang),
        run.workspace_name,
        // A run in flight carries its Stop beside the pill; the column keeps
        // its width either way (COLUMNS above), so a row settling to Aborted
        // moves nothing.
        <span key="status" className="inline-flex items-center gap-2">
          <RunStatusPill run={run} t={t} />
          {stoppable?.has(run.workspace_id) && <StopRunButton run={run} />}
        </span>,
        // The stage the engine last dispatched — reported, not interpreted. A
        // rerun rewrites it to the re-triggered step, so it is not evidence
        // that a run stopped there. `stageLabel` returns the English source
        // string; the dictionary carries the German for each known stage.
        run.current_stage ? t(stageLabel(run.current_stage)) : '—',
        formatNumber(run.total_papers_fetched, lang),
        formatNumber(run.total_papers_passed_screening, lang),
        formatDuration(run.duration_seconds, lang),
        formatUsd(run.usd_cost, lang),
        run.status_message ?? '—',
      ],
    }),
  )
  return <RunsTableFrame rows={rows} state="loaded" t={t} />
}

// Fixed per-row width patterns, never random, so screenshots and drift runs
// are stable. Header-dominated columns (dates, counts, duration) get bones
// narrower than their header so they add nothing to the column width; the
// stage and summary columns are cell-dominated and follow typical values.
// A `ch` is a digit's width and prose runs ~15% narrower, hence the fractions.
const DOMAIN_WIDTHS = ['18.8ch', '18.8ch', '13ch']
const STAGE_WIDTHS = ['7.5ch', '15ch', '8.5ch']
const SUMMARY_WIDTHS = ['28rem', '28rem', '16rem']

/** The table's loading state: the real headers over `rows` bone rows. */
export function RunsTableSkeleton({ rows = 8, t = (s) => s }: { rows?: number; t?: T }) {
  const bones = Array.from(
    { length: rows },
    (_, i): RunRow => ({
      key: `bone-${i}`,
      cells: [
        <Bone.Text key="started" widths={['11ch']} />,
        <Bone.Text key="domain" widths={[DOMAIN_WIDTHS[i % DOMAIN_WIDTHS.length]]} />,
        <Bone.Chip key="status" width={67} />,
        <Bone.Text key="stage" widths={[STAGE_WIDTHS[i % STAGE_WIDTHS.length]]} />,
        <Bone.Number key="fetched" digits={2} />,
        <Bone.Number key="passed" digits={2} />,
        <Bone.Text key="duration" widths={['6ch']} className="justify-end" />,
        <Bone.Text key="cost" widths={['4.4ch']} className="justify-end" />,
        <Bone.Text key="summary" widths={[SUMMARY_WIDTHS[i % SUMMARY_WIDTHS.length]]} />,
      ],
    }),
  )
  return <RunsTableFrame rows={bones} state="skeleton" t={t} />
}

/**
 * Shared presentation for run and step state. Server components, no client JS.
 *
 * The Studio is an operator surface and is written in English; `t()` falls back
 * to the source string, so switching the app to German leaves these untouched
 * until someone who knows the domain terms supplies them.
 */
import { Bone } from '@/components/skeleton'
import type { ComponentRun, ComponentSummary } from '@/lib/bff/component-runs/schema'
import type { PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import clsx from 'clsx'

/* --------------------------------- Values --------------------------------- */

/** The first eight characters of a run id — how a run is named on screen. */
export function shortId(id: string): string {
  return id.slice(0, 8)
}

/**
 * `0.84s`, `43.0s`, `1m 08s`, `3m 53s`, `2h 04m`. Null renders as an em dash.
 *
 * Rounds to whole seconds *before* splitting, so a duration like 119.7s cannot
 * render as `1m 60s` — the trap in rounding the remainder independently.
 */
export function formatDuration(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return '—'
  if (seconds < 0) return '—'
  if (seconds < 1) return `${seconds.toFixed(2)}s`
  if (seconds < 59.95) return `${seconds.toFixed(1)}s`
  const whole = Math.round(seconds)
  if (whole < 3600) {
    return `${Math.floor(whole / 60)}m ${String(whole % 60).padStart(2, '0')}s`
  }
  const hours = Math.floor(whole / 3600)
  return `${hours}h ${String(Math.floor((whole % 3600) / 60)).padStart(2, '0')}m`
}

/**
 * Spend, at a precision that suits the magnitude. `null` means the step
 * recorded no cost — rendered as an em dash, never as `$0.0000`, so an
 * unmeasured step can't be mistaken for a free one.
 */
export function formatUsd(usd: number | null): string {
  if (usd === null || !Number.isFinite(usd)) return '—'
  if (usd === 0) return '$0'
  // Sign goes outside the currency symbol, and the precision test uses the
  // magnitude so a small negative doesn't fall into the coarse branch.
  const sign = usd < 0 ? '-' : ''
  const magnitude = Math.abs(usd)
  return magnitude < 0.01 ? `${sign}$${magnitude.toFixed(4)}` : `${sign}$${magnitude.toFixed(2)}`
}

export function formatTokens(tokens: number | null): string {
  return tokens === null ? '—' : tokens.toLocaleString('en-US')
}

/* --------------------------------- Status --------------------------------- */

type Tone = 'ok' | 'warn' | 'bad' | 'busy' | 'idle'

const TONE_CLASS: Record<Tone, string> = {
  ok: 'bg-emerald-50 text-emerald-800 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-400/20',
  warn: 'bg-amber-50 text-amber-900 ring-amber-600/25 dark:bg-amber-400/10 dark:text-amber-200 dark:ring-amber-400/25',
  bad: 'bg-red-50 text-red-800 ring-red-600/20 dark:bg-red-500/10 dark:text-red-300 dark:ring-red-400/20',
  busy: 'bg-blue-50 text-blue-800 ring-blue-600/20 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-400/20',
  idle: 'bg-zinc-100 text-zinc-700 ring-zinc-500/20 dark:bg-zinc-400/10 dark:text-zinc-300 dark:ring-zinc-400/20',
}

function Pill({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-sm px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap ring-1 ring-inset',
        TONE_CLASS[tone],
      )}
    >
      {tone === 'busy' && (
        <span aria-hidden="true" className="size-1.5 animate-pulse rounded-full bg-current" />
      )}
      {children}
    </span>
  )
}

/**
 * A run's outcome — Django's `status` and nothing more.
 *
 * Deliberately does NOT try to infer "halted early" from `current_stage`: that
 * field is the last stage *dispatched*, and a rerun rewrites it to the
 * re-triggered step, so a fully-complete run can carry an early stage name.
 * Whether a run really stopped short is visible in its step timeline, which is
 * evidence rather than inference.
 */
export function RunStatus({ run }: { run: Pick<PipelineRun, 'status'> }) {
  switch (run.status) {
    case 'completed':
      return <Pill tone="ok">Completed</Pill>
    case 'running':
      return <Pill tone="busy">Running</Pill>
    case 'failed':
      return <Pill tone="bad">Failed</Pill>
    case 'aborted':
      return <Pill tone="idle">Aborted</Pill>
    default:
      return <Pill tone="idle">Pending</Pill>
  }
}

const STEP_TONE: Record<ComponentRun['status'], Tone> = {
  completed: 'ok',
  running: 'busy',
  failed: 'bad',
  aborted: 'idle',
  skipped: 'idle',
  pending: 'idle',
}

export function StepStatus({ status }: { status: ComponentRun['status'] }) {
  const label = status.charAt(0).toUpperCase() + status.slice(1)
  return <Pill tone={STEP_TONE[status]}>{label}</Pill>
}

/* -------------------------------- Summaries -------------------------------- */

function Count({ value, label, tone }: { value: number; label: string; tone?: 'good' | 'bad' }) {
  return (
    <span className="whitespace-nowrap">
      <span
        className={clsx(
          'font-medium tabular-nums',
          tone === 'good' && 'text-emerald-700 dark:text-emerald-400',
          tone === 'bad' && 'text-red-700 dark:text-red-400',
          !tone && 'text-zinc-900 dark:text-zinc-100',
        )}
      >
        {value.toLocaleString('en-US')}
      </span>{' '}
      <span className="text-zinc-500 dark:text-zinc-400">{label}</span>
    </span>
  )
}

// One line of counts; shared with StepSummarySkeleton so the bones sit on the
// same baseline grid as the loaded counts.
const SUMMARY_WRAP = 'flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-xs'

/**
 * What a step did, read off the typed summary the BFF resolved. `kind: 'none'`
 * says so plainly rather than showing a zero the engine never reported.
 */
export function StepSummary({ summary }: { summary: ComponentSummary }) {
  const wrap = SUMMARY_WRAP
  switch (summary.kind) {
    case 'search':
      return (
        <div className={wrap}>
          <Count value={summary.created} label="new" tone="good" />
          <Count value={summary.fetched} label="fetched" />
          {summary.duplicates > 0 && <Count value={summary.duplicates} label="duplicates" />}
        </div>
      )
    case 'download':
      return (
        <div className={wrap}>
          <Count value={summary.downloaded} label="downloaded" />
          {summary.cached > 0 && <Count value={summary.cached} label="cached" />}
          {summary.failed > 0 && <Count value={summary.failed} label="failed" tone="bad" />}
        </div>
      )
    case 'ocr':
      return (
        <div className={wrap}>
          <Count value={summary.converted} label="converted" />
          {summary.failed > 0 && <Count value={summary.failed} label="failed" tone="bad" />}
        </div>
      )
    case 'screening':
      return (
        <div className={wrap}>
          <Count value={summary.screened} label="screened" />
          <Count value={summary.passed} label="passed" tone="good" />
          {summary.rejected > 0 && <Count value={summary.rejected} label="rejected" tone="bad" />}
          {summary.withdrawn > 0 && <Count value={summary.withdrawn} label="withdrawn" />}
        </div>
      )
    case 'extraction':
      return (
        <div className={wrap}>
          <Count value={summary.created} label="extractions" tone="good" />
          <Count value={summary.papers} label="papers" />
          <Count value={summary.definitions} label="definitions" />
          {summary.failed > 0 && <Count value={summary.failed} label="failed" tone="bad" />}
        </div>
      )
    case 'signal_score':
      return (
        <div className={wrap}>
          <Count value={summary.scored} label={`of ${summary.total} scored`} />
          {summary.avg !== null && (
            <span className="whitespace-nowrap text-zinc-500 dark:text-zinc-400">
              avg{' '}
              <span className="font-medium text-zinc-900 tabular-nums dark:text-zinc-100">
                {summary.avg.toFixed(1)}
              </span>
            </span>
          )}
          {summary.max !== null && (
            <span className="whitespace-nowrap text-zinc-500 dark:text-zinc-400">
              max{' '}
              <span className="font-medium text-zinc-900 tabular-nums dark:text-zinc-100">
                {summary.max.toFixed(1)}
              </span>
            </span>
          )}
        </div>
      )
    case 'reporting':
      return (
        <div className={wrap}>
          <span className="text-zinc-500 dark:text-zinc-400">
            {summary.generated ? 'Report generated' : 'No report'}
          </span>
          {summary.characters !== null && <Count value={summary.characters} label="characters" />}
        </div>
      )
    case 'none':
      return (
        <div className="text-xs text-zinc-400 italic dark:text-zinc-500">No metrics recorded</div>
      )
  }
}

/** One line of count bones, on the same baseline grid as StepSummary. */
export function StepSummarySkeleton({ counts = 3 }: { counts?: number }) {
  return (
    <div className={SUMMARY_WRAP}>
      {Array.from({ length: counts }, (_, i) => (
        <Bone.Text key={i} widths={['9ch']} />
      ))}
    </div>
  )
}

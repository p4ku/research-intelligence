/**
 * Shared presentation for run and step state. Server components, no client JS.
 *
 * Fully translatable: every visible word goes through `t()` and every number
 * through the locale-aware helpers in `@/lib/i18n`. Durations and spend are
 * formatted here rather than by Intl because their shape is fixed by the
 * column widths (`0.84s` / `0,84 s`, `2h 04m` / `2 Std. 04 Min.`), and the
 * German forms follow the terminology sheet. `t` and `lang` default to
 * English so the studio skeleton gallery can render these on fixtures without
 * a language context.
 */
import { Bone } from '@/components/skeleton'
import type { ComponentRun, ComponentSummary } from '@/lib/bff/component-runs/schema'
import type { PipelineRun } from '@/lib/bff/pipeline-runs/schema'
import { fmt, formatNumber, type Lang, type T } from '@/lib/i18n'
import { formatScore } from '@/lib/papers/select'
import clsx from 'clsx'

/* --------------------------------- Values --------------------------------- */

/** The first eight characters of a run id — how a run is named on screen. */
export function shortId(id: string): string {
  return id.slice(0, 8)
}

/**
 * `0.84s`, `43.0s`, `1m 08s`, `3m 53s`, `2h 04m`. Null renders as an em dash.
 * In German the same magnitudes read `0,84 s`, `43,0 s`, `1 Min. 08 s`,
 * `2 Std. 04 Min.` — decimal comma, DIN abbreviations, U+202F before units
 * (the same narrow no-break space formatPercent uses).
 *
 * Rounds to whole seconds *before* splitting, so a duration like 119.7s cannot
 * render as `1m 60s` — the trap in rounding the remainder independently.
 */
export function formatDuration(seconds: number | null, lang: Lang = 'en'): string {
  if (seconds === null || !Number.isFinite(seconds)) return '—'
  if (seconds < 0) return '—'
  const german = lang === 'de'
  if (seconds < 1) {
    return german ? `${formatNumber(seconds, lang, 2)}\u202fs` : `${seconds.toFixed(2)}s`
  }
  if (seconds < 59.95) {
    return german ? `${formatNumber(seconds, lang, 1)}\u202fs` : `${seconds.toFixed(1)}s`
  }
  const whole = Math.round(seconds)
  if (whole < 3600) {
    const minutes = Math.floor(whole / 60)
    const rest = String(whole % 60).padStart(2, '0')
    return german ? `${minutes}\u202fMin. ${rest}\u202fs` : `${minutes}m ${rest}s`
  }
  const hours = Math.floor(whole / 3600)
  const minutes = String(Math.floor((whole % 3600) / 60)).padStart(2, '0')
  return german ? `${hours}\u202fStd. ${minutes}\u202fMin.` : `${hours}h ${minutes}m`
}

/**
 * Spend, at a precision that suits the magnitude. `null` means the step
 * recorded no cost — rendered as an em dash, never as `$0.0000`, so an
 * unmeasured step can't be mistaken for a free one. German puts the symbol
 * after the amount (`12,34 $`, U+202F before it like formatPercent and
 * formatDuration), English before it (`$1,234.50`).
 */
export function formatUsd(usd: number | null, lang: Lang = 'en'): string {
  if (usd === null || !Number.isFinite(usd)) return '—'
  const german = lang === 'de'
  if (usd === 0) return german ? '0 $' : '$0'
  // Sign goes outside the currency symbol, and the precision test uses the
  // magnitude so a small negative doesn't fall into the coarse branch.
  const sign = usd < 0 ? '-' : ''
  const magnitude = Math.abs(usd)
  const amount = formatNumber(magnitude, lang, magnitude < 0.01 ? 4 : 2)
  return german ? `${sign}${amount} $` : `${sign}$${amount}`
}

export function formatTokens(tokens: number | null, lang: Lang = 'en'): string {
  return tokens === null ? '—' : formatNumber(tokens, lang)
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

const RUN_TONE: Record<PipelineRun['status'], Tone> = {
  completed: 'ok',
  running: 'busy',
  failed: 'bad',
  aborted: 'idle',
  pending: 'idle',
}

/**
 * The status word for a run. A switch over the enum, not a capitalisation of
 * it: the label is a translatable string, and an untranslated `t('running')`
 * would silently ship the wire value to a German reader.
 */
export function runStatusLabel(status: PipelineRun['status'], t: T): string {
  switch (status) {
    case 'completed':
      return t('Completed')
    case 'running':
      return t('Running')
    case 'failed':
      return t('Failed')
    case 'aborted':
      return t('Aborted')
    case 'pending':
      return t('Pending')
  }
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
export function RunStatus({ run, t = (s) => s }: { run: Pick<PipelineRun, 'status'>; t?: T }) {
  return <Pill tone={RUN_TONE[run.status]}>{runStatusLabel(run.status, t)}</Pill>
}

const STEP_TONE: Record<ComponentRun['status'], Tone> = {
  completed: 'ok',
  running: 'busy',
  failed: 'bad',
  aborted: 'idle',
  skipped: 'idle',
  pending: 'idle',
}

/** The status word for one step; `skipped` is the only one a run never has. */
export function stepStatusLabel(status: ComponentRun['status'], t: T): string {
  return status === 'skipped' ? t('Skipped') : runStatusLabel(status, t)
}

export function StepStatus({ status, t = (s) => s }: { status: ComponentRun['status']; t?: T }) {
  return <Pill tone={STEP_TONE[status]}>{stepStatusLabel(status, t)}</Pill>
}

/* -------------------------------- Summaries -------------------------------- */

function Count({
  value,
  label,
  tone,
  lang = 'en',
}: {
  value: number
  label: string
  tone?: 'good' | 'bad'
  lang?: Lang
}) {
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
        {formatNumber(value, lang)}
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
export function StepSummary({
  summary,
  t = (s) => s,
  lang = 'en',
}: {
  summary: ComponentSummary
  t?: T
  lang?: Lang
}) {
  const wrap = SUMMARY_WRAP
  switch (summary.kind) {
    case 'search':
      return (
        <div className={wrap}>
          <Count value={summary.created} label={t('new')} tone="good" lang={lang} />
          <Count value={summary.fetched} label={t('fetched')} lang={lang} />
          {summary.duplicates > 0 && (
            <Count value={summary.duplicates} label={t('duplicates')} lang={lang} />
          )}
        </div>
      )
    case 'download':
      return (
        <div className={wrap}>
          <Count value={summary.downloaded} label={t('downloaded')} lang={lang} />
          {summary.cached > 0 && <Count value={summary.cached} label={t('cached')} lang={lang} />}
          {summary.failed > 0 && (
            <Count value={summary.failed} label={t('failed')} tone="bad" lang={lang} />
          )}
        </div>
      )
    case 'ocr':
      return (
        <div className={wrap}>
          <Count value={summary.converted} label={t('converted')} lang={lang} />
          {summary.failed > 0 && (
            <Count value={summary.failed} label={t('failed')} tone="bad" lang={lang} />
          )}
        </div>
      )
    case 'screening':
      return (
        <div className={wrap}>
          <Count value={summary.screened} label={t('screened')} lang={lang} />
          <Count value={summary.passed} label={t('passed')} tone="good" lang={lang} />
          {summary.rejected > 0 && (
            <Count value={summary.rejected} label={t('rejected')} tone="bad" lang={lang} />
          )}
          {summary.withdrawn > 0 && (
            <Count value={summary.withdrawn} label={t('withdrawn')} lang={lang} />
          )}
        </div>
      )
    case 'extraction':
      return (
        <div className={wrap}>
          <Count value={summary.created} label={t('extractions')} tone="good" lang={lang} />
          <Count value={summary.papers} label={t('papers')} lang={lang} />
          <Count value={summary.definitions} label={t('definitions')} lang={lang} />
          {summary.failed > 0 && (
            <Count value={summary.failed} label={t('failed')} tone="bad" lang={lang} />
          )}
        </div>
      )
    case 'signal_score':
      return (
        <div className={wrap}>
          <Count
            value={summary.scored}
            label={fmt(t('of {total} scored'), { total: formatNumber(summary.total, lang) })}
            lang={lang}
          />
          {summary.avg !== null && (
            <span className="whitespace-nowrap text-zinc-500 dark:text-zinc-400">
              {t('avg')}{' '}
              <span className="font-medium text-zinc-900 tabular-nums dark:text-zinc-100">
                {formatScore(summary.avg)}
              </span>
            </span>
          )}
          {summary.max !== null && (
            <span className="whitespace-nowrap text-zinc-500 dark:text-zinc-400">
              {t('max')}{' '}
              <span className="font-medium text-zinc-900 tabular-nums dark:text-zinc-100">
                {formatScore(summary.max)}
              </span>
            </span>
          )}
        </div>
      )
    case 'reporting':
      return (
        <div className={wrap}>
          <span className="text-zinc-500 dark:text-zinc-400">
            {summary.generated ? t('Report generated') : t('No report')}
          </span>
          {summary.characters !== null && (
            <Count value={summary.characters} label={t('characters')} lang={lang} />
          )}
        </div>
      )
    case 'none':
      return (
        <div className="text-xs text-zinc-400 italic dark:text-zinc-500">
          {t('No metrics recorded')}
        </div>
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

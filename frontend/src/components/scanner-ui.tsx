import { AnswerMarkdown } from '@/components/answer-markdown'
import { Sparkline } from '@/components/charts'
import { Bone } from '@/components/skeleton'
import type { T } from '@/lib/i18n'
import type { Dimension, ScreeningStatus } from '@/lib/papers/types'
import { ArrowDownIcon, ArrowRightIcon, ExclamationTriangleIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import Link from 'next/link'

/* -------------------------------- Breadcrumbs ------------------------------- */

// Location trail in the app's mono-eyebrow style. The final item is the
// current page (rendered emphasised, not linked); earlier items link up.
export function Breadcrumbs({
  items,
  t = (s) => s,
}: {
  items: { label: string; href?: string }[]
  t?: T
}) {
  return (
    <nav
      aria-label={t('Breadcrumb')}
      className="flex max-w-full items-center gap-2 font-mono text-[11px] tracking-[0.14em] uppercase"
    >
      {items.map((item, i) => {
        const isLast = i === items.length - 1
        return (
          <span key={i} className="flex min-w-0 items-center gap-2">
            {item.href && !isLast ? (
              <Link
                href={item.href}
                className="shrink-0 text-zinc-400 transition-colors hover:text-zinc-700 dark:text-zinc-500 dark:hover:text-zinc-200"
              >
                {item.label}
              </Link>
            ) : (
              <span
                className={clsx(
                  'truncate',
                  isLast
                    ? 'text-zinc-950 dark:text-white'
                    : 'shrink-0 text-zinc-400 dark:text-zinc-500',
                )}
              >
                {item.label}
              </span>
            )}
            {!isLast && (
              <span aria-hidden="true" className="shrink-0 text-zinc-300 dark:text-zinc-600">
                /
              </span>
            )}
          </span>
        )
      })}
    </nav>
  )
}

/* -------------------------------- Page header ------------------------------- */

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: React.ReactNode
  title: string
  description?: string
  actions?: React.ReactNode
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && (
          <div className="flex items-center text-xs font-semibold tracking-[0.18em] text-zinc-400 uppercase dark:text-zinc-500">
            <span aria-hidden="true" className="bg-accent mr-2 inline-block size-1.5" />
            {eyebrow}
          </div>
        )}
        <h1 className="mt-1 text-[26px]/8 font-semibold tracking-tight text-zinc-950 dark:text-white">
          {title}
        </h1>
        {description && (
          <p className="mt-1.5 max-w-2xl text-sm text-zinc-500 dark:text-zinc-400">{description}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}

export function SectionLabel({
  children,
  className,
  size = 'xs',
}: {
  children: React.ReactNode
  className?: string
  /** 'sm' bumps the label a step for sections that should read louder. */
  size?: 'xs' | 'sm'
}) {
  return (
    <h2
      className={clsx(
        'text-foreground flex items-center font-semibold tracking-[0.18em] uppercase',
        size === 'sm' ? 'text-sm' : 'text-xs',
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={clsx('bg-accent mr-2 inline-block', size === 'sm' ? 'size-2' : 'size-1.5')}
      />
      {children}
    </h2>
  )
}

/* ----------------------------------- Card ----------------------------------- */

// Raised surface: a crisp hairline plus a soft two-layer ambient shadow so white
// cards lift off the near-white page field. Dark mode already separates surface
// from background by lightness, so it falls back to a plain border, no shadow.
const raisedSurface =
  'border-line-strong bg-surface rounded-sm border shadow-[0_1px_2px_rgba(19,19,17,0.05),0_5px_14px_-4px_rgba(19,19,17,0.10)] dark:border-line dark:shadow-none'

export function Card({ className, children, ...props }: React.ComponentPropsWithoutRef<'div'>) {
  return (
    <div {...props} className={clsx(raisedSurface, 'p-5', className)}>
      {children}
    </div>
  )
}

/* --------------------------------- Stat tile -------------------------------- */

function StatTileFrame({
  label,
  value,
  bottom,
  state,
}: {
  label: React.ReactNode
  value: React.ReactNode
  bottom: React.ReactNode
  state: 'loaded' | 'skeleton'
}) {
  // Not a Card: an inset well recessed to the page background — no elevation.
  return (
    <div
      data-shape="stat-tile"
      data-state={state}
      className="border-line-soft bg-background flex flex-col gap-1 rounded-sm border p-5"
    >
      <div data-row="label" className="text-sm text-zinc-500 dark:text-zinc-400">
        {label}
      </div>
      <div
        data-row="value"
        className="font-mono text-3xl font-medium tracking-tight text-zinc-950 tabular-nums dark:text-white"
      >
        {value}
      </div>
      <div data-row="sub" className="flex items-center gap-2 text-xs">
        {bottom}
      </div>
    </div>
  )
}

export function StatTile({
  label,
  value,
  sub,
  delta,
}: {
  label: string
  value: string | number
  sub?: string
  delta?: number
}) {
  return (
    <StatTileFrame
      state="loaded"
      label={label}
      value={value}
      bottom={
        <>
          {typeof delta === 'number' && <DeltaBadge delta={delta} />}
          {sub && <span className="text-zinc-500 dark:text-zinc-400">{sub}</span>}
        </>
      }
    />
  )
}

export function StatTileSkeleton({ digits = 3 }: { digits?: number }) {
  return (
    <StatTileFrame
      state="skeleton"
      label={<Bone.Text widths={['9ch']} />}
      value={<Bone.Number digits={digits} />}
      bottom={<Bone.Text widths={['12ch']} />}
    />
  )
}

/* --------------------------------- Stat band --------------------------------- */

export interface StatBandItem {
  label: string
  value: string | number
  /** Small caption shown when there is no sparkline (e.g. "all sources, 90 days"). */
  sub?: string
  delta?: number
  spark?: number[]
}

/**
 * A row of headline stats separated by hairline dividers instead of boxed
 * cards: label, big mono number, inline delta, and a sparkline (or caption)
 * underneath. Set `flow` when the stats form a pipeline — each stage after
 * the first gets a → prefix. Set `orientation="vertical"` to stack the stats
 * in a single column (e.g. as a narrow side rail); flow arrows point down.
 */
/** One rendered cell of a StatBand: shared by the loaded band and its skeleton. */
interface StatBandCell {
  key: string
  label: React.ReactNode
  value: React.ReactNode
  delta?: React.ReactNode
  below?: React.ReactNode
}

// The band chrome for both orientations. Slots receive fully-wrapped nodes;
// every layout class lives here so StatBandSkeleton cannot drift from the
// loaded band (measured by scripts/skeleton-drift.ts via data-shape/data-row).
function StatBandFrame({
  cells,
  flow = false,
  orientation = 'horizontal',
  state,
  className,
}: {
  cells: StatBandCell[]
  flow?: boolean
  orientation?: 'horizontal' | 'vertical'
  state: 'loaded' | 'skeleton'
  className?: string
}) {
  if (orientation === 'vertical') {
    return (
      <div
        data-shape="stat-band"
        data-state={state}
        className={clsx(
          'border-line-soft flex flex-col divide-y divide-zinc-950/5 border-y dark:divide-white/5',
          className,
        )}
      >
        {cells.map((cell, i) => (
          <div
            key={cell.key}
            data-row="cell"
            className="flex items-baseline justify-between gap-4 py-3.5"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 text-sm text-zinc-500 dark:text-zinc-400">
                {flow && i > 0 && (
                  <ArrowDownIcon className="size-3 shrink-0 text-zinc-300 dark:text-zinc-600" />
                )}
                <span className="truncate">{cell.label}</span>
              </div>
              {cell.below}
            </div>
            <div className="flex shrink-0 items-baseline gap-2">
              {cell.delta}
              <span className="font-mono text-3xl font-medium tracking-tight text-zinc-950 tabular-nums dark:text-white">
                {cell.value}
              </span>
            </div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div
      data-shape="stat-band"
      data-state={state}
      className={clsx(
        'border-line-soft grid grid-cols-2 gap-x-4 gap-y-6 border-y py-5 lg:grid-cols-4 lg:gap-x-0 lg:divide-x lg:divide-zinc-950/5 lg:dark:divide-white/5',
        className,
      )}
    >
      {cells.map((cell, i) => (
        <div key={cell.key} data-row="cell" className="lg:px-6 lg:first:pl-0 lg:last:pr-0">
          <div className="flex items-center gap-1.5 text-sm text-zinc-500 dark:text-zinc-400">
            {flow && i > 0 && (
              <ArrowRightIcon className="size-3 shrink-0 text-zinc-300 dark:text-zinc-600" />
            )}
            <span className="truncate">{cell.label}</span>
          </div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="font-mono text-3xl font-medium tracking-tight text-zinc-950 tabular-nums dark:text-white">
              {cell.value}
            </span>
            {cell.delta}
          </div>
          {cell.below}
        </div>
      ))}
    </div>
  )
}

export function StatBand({
  items,
  flow = false,
  orientation = 'horizontal',
  className,
}: {
  items: StatBandItem[]
  flow?: boolean
  orientation?: 'horizontal' | 'vertical'
  className?: string
}) {
  const vertical = orientation === 'vertical'
  const cells = items.map(
    (item): StatBandCell => ({
      key: item.label,
      label: item.label,
      value: item.value,
      delta: typeof item.delta === 'number' ? <DeltaBadge delta={item.delta} /> : undefined,
      below: vertical ? (
        item.sub && (
          <div className="mt-0.5 text-[11px] text-zinc-400 dark:text-zinc-500">{item.sub}</div>
        )
      ) : item.spark ? (
        <Sparkline data={item.spark} width={96} height={24} className="mt-2" />
      ) : (
        item.sub && (
          <div className="mt-2 text-[11px] text-zinc-400 dark:text-zinc-500">{item.sub}</div>
        )
      ),
    }),
  )
  return (
    <StatBandFrame
      cells={cells}
      flow={flow}
      orientation={orientation}
      state="loaded"
      className={className}
    />
  )
}

/**
 * The band's loading state. Pass the real `labels`/`subs` when the copy is
 * static (e.g. the dashboard funnel) so only the numbers are bones; `digits`
 * sizes the number bones in mono ch.
 */
export function StatBandSkeleton({
  count = 4,
  labels,
  subs,
  digits = 3,
  withDelta = false,
  below = 'sub',
  flow = false,
  orientation = 'horizontal',
  className,
}: {
  count?: number
  labels?: string[]
  subs?: string[]
  digits?: number
  withDelta?: boolean
  below?: 'sub' | 'spark' | 'none'
  flow?: boolean
  orientation?: 'horizontal' | 'vertical'
  className?: string
}) {
  const vertical = orientation === 'vertical'
  const subWrap = vertical
    ? 'mt-0.5 text-[11px] text-zinc-400 dark:text-zinc-500'
    : 'mt-2 text-[11px] text-zinc-400 dark:text-zinc-500'
  const cells = Array.from(
    { length: count },
    (_, i): StatBandCell => ({
      key: labels?.[i] ?? `bone-${i}`,
      label: labels?.[i] ?? <Bone.Text widths={['9ch']} />,
      value: <Bone.Number digits={digits} />,
      delta: withDelta ? (
        <Bone.Text widths={['3ch']} className="font-mono text-[11px]" />
      ) : undefined,
      below:
        below === 'none' || (vertical && below === 'spark') ? undefined : below === 'spark' ? (
          <Bone.Block className="mt-2 h-6 w-24" />
        ) : (
          <div className={subWrap}>{subs?.[i] ?? <Bone.Text widths={['60%']} />}</div>
        ),
    }),
  )
  return (
    <StatBandFrame
      cells={cells}
      flow={flow}
      orientation={orientation}
      state="skeleton"
      className={className}
    />
  )
}

export function DeltaBadge({ delta, suffix = '' }: { delta: number; suffix?: string }) {
  const up = delta >= 0
  return (
    <span
      className={clsx(
        'inline-flex items-center font-mono text-[11px] font-medium tracking-[0.07em] uppercase tabular-nums',
        up ? 'text-positive' : 'text-negative',
      )}
    >
      {up ? '+' : '−'}
      {Math.abs(delta)}
      {suffix}
    </span>
  )
}

/* ------------------------------- Sector chip -------------------------------- */

/* --------------------------------- TRL badge -------------------------------- */

// This file is imported by both server and client components, so translation
// arrives as an optional prop (default: identity) instead of getT/useT.
export function TrlBadge({ trl, t = (s) => s }: { trl: number; t?: T }) {
  // TRL bands: 1–3 research, 4–6 development, 7–9 deployment.
  const band = trl <= 3 ? t('Research') : trl <= 6 ? t('Development') : t('Deployment')
  return (
    <span className="bg-foreground/6 inline-flex items-center gap-1.5 rounded-sm px-2 py-0.5 text-xs font-medium text-zinc-700 dark:text-zinc-200">
      <span className="font-mono tabular-nums">TRL {trl}</span>
      <span className="text-zinc-400 dark:text-zinc-500">·</span>
      <span className="text-zinc-500 dark:text-zinc-400">{band}</span>
    </span>
  )
}

/* ------------------------------ Signal score ring --------------------------- */

export function SignalScore({
  score,
  size = 'md',
}: {
  score: number | null
  size?: 'sm' | 'md' | 'lg'
}) {
  const dims = { sm: 40, md: 52, lg: 68 }[size]
  const stroke = size === 'lg' ? 5 : 4
  const r = (dims - stroke) / 2
  const c = 2 * Math.PI * r
  // The ring assumes 0–100; the workspace formula may return anything, so
  // clamp the arc and print the number as it is.
  const pct = score === null ? 0 : Math.max(0, Math.min(100, score)) / 100
  // Score color: high = accent (signal strength), mid = Zitrus, low = neutral.
  const color =
    score !== null && score >= 75
      ? 'var(--accent)'
      : score !== null && score >= 55
        ? 'var(--warn)'
        : '#9a9a90'
  const fontSize = size === 'lg' ? 20 : size === 'md' ? 15 : 12
  const label = score === null ? '—' : Number.isInteger(score) ? String(score) : score.toFixed(1)
  return (
    <div
      className="relative inline-flex items-center justify-center"
      style={{ width: dims, height: dims }}
      title={score === null ? undefined : String(score)}
    >
      <svg width={dims} height={dims} className="-rotate-90">
        <circle
          cx={dims / 2}
          cy={dims / 2}
          r={r}
          fill="none"
          strokeWidth={stroke}
          className="stroke-zinc-950/8 dark:stroke-white/10"
        />
        {score !== null && (
          <circle
            cx={dims / 2}
            cy={dims / 2}
            r={r}
            fill="none"
            strokeWidth={stroke}
            stroke={color}
            strokeLinecap="butt"
            strokeDasharray={c}
            strokeDashoffset={c * (1 - pct)}
            className="transition-[stroke-dashoffset,stroke] duration-[250ms] ease-out"
          />
        )}
      </svg>
      <span
        className={clsx(
          'absolute font-mono font-medium tabular-nums',
          score === null ? 'text-zinc-400 dark:text-zinc-500' : 'text-zinc-950 dark:text-white',
        )}
        style={{ fontSize: label.length > 3 ? fontSize * 0.8 : fontSize }}
      >
        {label}
      </span>
    </div>
  )
}

/* ------------------------------ Score bar row ------------------------------- */

export function ScoreRow({
  label,
  value,
  max = 100,
  raw,
  color = 'var(--accent)',
  rationale,
  evidence,
  meta,
}: {
  label: string
  value: number | null
  /** null → no bar, the raw string is shown instead. */
  max?: number | null
  raw?: string
  color?: string
  rationale?: string
  evidence?: string[]
  /** Small tags rendered after the value (confidence, review flags). */
  meta?: React.ReactNode
}) {
  const hasBar = value !== null && max !== null && max > 0
  const pct = hasBar ? Math.max(0, Math.min(100, (value / max) * 100)) : 0
  const shown =
    value === null
      ? (raw ?? '—')
      : Number.isInteger(value)
        ? String(value)
        : (Math.round(value * 100) / 100).toString()
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="min-w-0 truncate text-sm font-medium text-zinc-700 dark:text-zinc-200">
          {label}
        </span>
        <span className="flex shrink-0 items-baseline gap-2">
          {meta}
          <span
            className={clsx(
              'font-mono text-sm font-medium tabular-nums',
              value === null ? 'text-zinc-500 dark:text-zinc-400' : 'text-zinc-950 dark:text-white',
            )}
          >
            {shown}
            {hasBar && max !== 100 ? `/${max}` : ''}
          </span>
        </span>
      </div>
      {hasBar && (
        <div className="bg-line-soft mt-1.5 h-[3px] w-full overflow-hidden">
          {/* scaleX rather than width so the glide runs off the main thread */}
          <div
            className="h-full w-full origin-left transition-transform duration-[250ms] ease-out"
            style={{ transform: `scaleX(${pct / 100})`, backgroundColor: color }}
          />
        </div>
      )}
      {rationale && (
        <AnswerMarkdown
          text={rationale}
          className="mt-1.5 text-xs text-zinc-500 dark:text-zinc-400"
        />
      )}
      {evidence && evidence.length > 0 && (
        <ul className="mt-1.5 space-y-1">
          {evidence.map((quote, i) => (
            <li
              key={i}
              className="border-line-soft border-l-2 pl-2 text-xs leading-relaxed text-zinc-500 italic dark:text-zinc-400"
            >
              “{quote}”
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/* ------------------------------ Screening pill ------------------------------ */

const screeningLabels: Record<ScreeningStatus, string> = {
  pending: 'Pending',
  abstract_passed: 'Abstract passed',
  full_text_passed: 'Full text passed',
  accepted: 'Accepted',
  borderline: 'Borderline',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
}

const screeningStyles: Record<ScreeningStatus, string> = {
  pending: 'bg-foreground/6 text-muted-foreground',
  abstract_passed: 'bg-positive/12 text-positive dark:bg-positive/15',
  full_text_passed: 'bg-positive/12 text-positive dark:bg-positive/15',
  accepted: 'bg-positive/12 text-positive dark:bg-positive/15',
  borderline: 'bg-warn/15 text-warn-ink dark:bg-warn/10',
  rejected: 'bg-red-500/10 text-red-700 dark:bg-red-500/15 dark:text-red-300',
  withdrawn: 'bg-foreground/6 text-muted-foreground line-through',
}

export function screeningLabel(status: ScreeningStatus, t: T = (s) => s): string {
  return t(screeningLabels[status])
}

// Same server/client split as TrlBadge: translation arrives as a prop.
export function ScreeningPill({
  status,
  t = (s) => s,
  className,
}: {
  status: ScreeningStatus
  t?: T
  className?: string
}) {
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-sm px-2 py-0.5 text-xs font-medium',
        screeningStyles[status],
        className,
      )}
    >
      {screeningLabel(status, t)}
    </span>
  )
}

/* --------------------------- Paper score axes helper ------------------------ */

/** Radar axes from the numeric, scaled dimensions (0–100 each). */
export function dimensionRadarAxes(dimensions: Dimension[]) {
  return dimensions
    .filter((d) => d.value !== null && d.max !== null && d.max > 0)
    .map((d) => ({ label: d.name, value: Math.max(0, Math.min(100, (d.value! / d.max!) * 100)) }))
}

/* --------------------------------- TLDR callout ------------------------------ */

export function Tldr({
  label = 'TLDR',
  children,
  className,
}: {
  label?: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={clsx('border-accent/40 bg-accent/6 rounded-sm border p-4', className)}>
      <div className="text-accent font-mono text-[11px] font-medium tracking-[0.18em] uppercase">
        {label}
      </div>
      <div className="mt-1.5 text-sm leading-relaxed text-zinc-700 dark:text-zinc-200">
        {children}
      </div>
    </div>
  )
}

export function LinkCard({
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
        'group hover:border-foreground/25 dark:hover:border-foreground/20 block p-5 transition-[border-color,box-shadow,transform] duration-150 ease-out hover:shadow-[0_2px_4px_rgba(19,19,17,0.06),0_10px_24px_-6px_rgba(19,19,17,0.14)] active:scale-[0.99] dark:hover:shadow-none',
        raisedSurface,
        className,
      )}
    >
      {children}
    </Link>
  )
}

/* -------------------------------- ErrorNote -------------------------------- */

// The single inline error presentation: tinted panel, icon, message, optional
// action slot. `role="alert"` announces it when it appears. Error ink is
// `--negative` (5.6:1 on white) — `--warn` is a chart/badge fill, not a text
// colour (see route-error.test.tsx, which pins both).
export function ErrorNote({
  action,
  className,
  children,
}: {
  action?: React.ReactNode
  className?: string
  children: React.ReactNode
}) {
  return (
    <div
      role="alert"
      className={clsx(
        'border-negative/40 bg-negative/5 flex items-start gap-2 rounded-sm border px-3 py-2.5',
        className,
      )}
    >
      <ExclamationTriangleIcon
        aria-hidden="true"
        className="text-negative mt-0.5 size-4 shrink-0"
      />
      <div className="min-w-0 flex-1">
        <div className="text-foreground/90 text-sm leading-relaxed">{children}</div>
        {action && <div className="mt-2">{action}</div>}
      </div>
    </div>
  )
}

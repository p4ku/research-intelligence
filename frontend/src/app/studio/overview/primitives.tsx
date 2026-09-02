/**
 * The overview's small vocabulary on the Souverän tokens: status chip, state
 * dot, 3px meter, section slab, message block. Client-safe (no directive):
 * both the client panes and the server-rendered skeletons import from here.
 */
import type { RunStatus } from '@/lib/bff/pipeline-runs/schema'
import clsx from 'clsx'
import type { ReactNode } from 'react'

export type Tone = 'pos' | 'neg' | 'acc' | 'mut' | 'warn' | 'plain'

const CHIP: Record<Tone, string> = {
  pos: 'text-positive border-positive/30 bg-positive/8',
  neg: 'text-negative border-negative/30 bg-negative/8',
  acc: 'text-accent-ink border-accent-ink/30 bg-accent/10',
  mut: 'text-muted-foreground border-line bg-foreground/3',
  warn: 'text-warn-ink border-warn-ink/30 bg-warn/15',
  plain: 'text-muted-foreground border-line bg-transparent',
}

const DOT: Record<Tone | 'none', string> = {
  pos: 'bg-positive',
  neg: 'bg-negative',
  acc: 'bg-accent',
  mut: 'bg-muted-foreground',
  warn: 'bg-warn',
  plain: 'bg-muted-foreground',
  none: 'bg-transparent ring-1 ring-inset ring-muted-foreground',
}

export const STATUS_TONE: Record<RunStatus, Tone> = {
  completed: 'pos',
  running: 'acc',
  failed: 'neg',
  aborted: 'neg',
  pending: 'mut',
}

export const STATUS_LABEL: Record<RunStatus, string> = {
  completed: 'Completed',
  running: 'Running',
  failed: 'Failed',
  aborted: 'Aborted',
  pending: 'Pending',
}

export const MONO = 'font-mono tabular-nums'

/** A square 6px state dot; `none` is an outlined square for "no runs". */
export function Dot({ tone, className }: { tone: Tone | 'none'; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={clsx('inline-block size-1.5 shrink-0 rounded-[2px]', DOT[tone], className)}
    />
  )
}

export function Chip({
  tone,
  dot = false,
  className,
  children,
}: {
  tone: Tone
  dot?: boolean
  className?: string
  children: ReactNode
}) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-sm border px-1.5 text-[11px] leading-[17px] font-medium whitespace-nowrap',
        CHIP[tone],
        className,
      )}
    >
      {dot && <Dot tone={tone} />}
      {children}
    </span>
  )
}

/** Colour always paired with the word. */
export function StatusChip({ status, className }: { status: RunStatus; className?: string }) {
  return (
    <Chip tone={STATUS_TONE[status]} dot className={className}>
      {STATUS_LABEL[status]}
    </Chip>
  )
}

/** 3px, squared. Warn from 80%, negative from 100%. Presentational. */
export function Meter({ percent, className }: { percent: number; className?: string }) {
  const width = Math.max(0, Math.min(100, percent))
  const fill = percent >= 100 ? 'bg-negative' : percent >= 80 ? 'bg-warn' : 'bg-accent'
  return (
    <span
      role="presentation"
      className={clsx('bg-line-soft block h-[3px] w-full overflow-hidden', className)}
    >
      <span className={clsx('block h-full', fill)} style={{ width: `${width.toFixed(1)}%` }} />
    </span>
  )
}

/** Section label with the 6×6 accent square; `as` picks the heading level. */
export function Slab({
  as: Tag = 'h3',
  children,
  count,
  className,
}: {
  as?: 'h2' | 'h3' | 'h4' | 'div'
  children: ReactNode
  /** Right-aligned mono count. */
  count?: ReactNode
  className?: string
}) {
  return (
    <Tag
      className={clsx(
        'text-foreground flex items-center gap-2 text-[11px] font-semibold tracking-[0.18em] uppercase',
        className,
      )}
    >
      <span aria-hidden="true" className="bg-accent inline-block size-1.5 shrink-0" />
      <span className="min-w-0 truncate">{children}</span>
      {count !== undefined && (
        <span
          className={clsx(
            MONO,
            'text-muted-foreground ml-auto text-[11px] font-normal tracking-normal normal-case',
          )}
        >
          {count}
        </span>
      )}
    </Tag>
  )
}

const MSG: Record<'neg' | 'acc' | 'mut', string> = {
  neg: 'border-negative bg-negative/5',
  acc: 'border-accent bg-accent/8',
  mut: 'border-line bg-foreground/3',
}

/** The engine's own words (status message, error message), set off by a 2px rule. */
export function Msg({
  tone,
  children,
  className,
}: {
  tone: 'neg' | 'acc' | 'mut'
  children: ReactNode
  className?: string
}) {
  return (
    <p
      className={clsx(
        'text-foreground border-l-2 px-2 py-1.5 text-xs leading-snug break-words',
        MSG[tone],
        className,
      )}
    >
      {children}
    </p>
  )
}

/** A dot separator that screen readers skip. */
export function Sep() {
  return (
    <span aria-hidden="true" className="text-muted-foreground">
      ·
    </span>
  )
}

/** The focus ring every control in the overview shares. */
export const FOCUS =
  'focus-visible:outline-accent-ink focus-visible:outline-2 focus-visible:-outline-offset-2'

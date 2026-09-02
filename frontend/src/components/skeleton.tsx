import clsx from 'clsx'
import type { ComponentPropsWithoutRef, CSSProperties, ReactNode } from 'react'

/**
 * Skeleton primitives ("bones"). A bone is an inert placeholder block; it never
 * animates itself — motion is one scan sweep per Skeleton.Region, driven by the
 * [data-skeleton]::after rules in styles/tailwind.css. Not animate-pulse: in
 * this app pulse means "this run/step is executing" (run-presentation,
 * step-timeline), while bones mean "not here yet".
 *
 * Sizing rules that keep skeletons honest (checked by scripts/skeleton-drift.ts):
 * - Bone.Text occupies exactly 1lh per line, so a paragraph is the same height
 *   loaded or not. It inherits font-size/line-height from the slot it sits in.
 * - Bone.Number reserves N digits (width in ch of the inherited font). Exact
 *   wherever digits are uniform: a font-mono slot or a tabular-nums sans cell.
 * - Percentage widths only in block contexts; inside flex rows use ch widths
 *   or Bone.Chip (a % width in a shrink-to-fit flex item resolves to 0).
 */

// 8% ink reads on both bg-surface (cards) and bg-background (wells); 2px
// radius like every other radius token — only dots and rings are round.
const BONE = 'bg-foreground/8 rounded-sm'

// Fixed line-width pattern, never random, so screenshots and drift runs are stable.
const PATTERN = ['100%', '88%', '46%']

function Text({
  lines = 1,
  widths = PATTERN,
  className,
}: {
  lines?: number
  /** One width per line, cycled; %, ch, or any CSS width. */
  widths?: string[]
  className?: string
}) {
  return (
    <>
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} className={clsx('flex h-[1lh] items-center', className)}>
          <span
            className={clsx(BONE, 'block h-[0.72em]')}
            style={{ width: widths[i % widths.length] }}
          />
        </span>
      ))}
    </>
  )
}

function Number({ digits = 3, className }: { digits?: number; className?: string }) {
  return (
    <span
      className={clsx('inline-flex h-[1lh] items-center align-top', className)}
      style={{ width: `${digits}ch` }}
    >
      <span className={clsx(BONE, 'block h-[0.72em] w-full')} />
    </span>
  )
}

function Chip({ width = 88, className }: { width?: number; className?: string }) {
  // 20px: the height of the app's pills and badges (text-xs line + py-0.5).
  return <span className={clsx(BONE, 'inline-block h-5 shrink-0', className)} style={{ width }} />
}

function Block({
  className,
  round = false,
  style,
}: {
  className?: string
  round?: boolean
  style?: CSSProperties
}) {
  return <span className={clsx(BONE, 'block', round && 'rounded-full', className)} style={style} />
}

function Dot({ size = 6, className }: { size?: number; className?: string }) {
  return (
    <span
      className={clsx('bg-foreground/8 inline-block shrink-0 rounded-full', className)}
      style={{ width: size, height: size }}
    />
  )
}

function Ring({
  size = 52,
  stroke = 4,
  className,
}: {
  size?: number
  stroke?: number
  className?: string
}) {
  // Stands in for SignalScore: the track only — no arc, no number.
  return (
    <span
      className={clsx('border-foreground/8 inline-block shrink-0 rounded-full', className)}
      style={{ width: size, height: size, borderWidth: stroke }}
    />
  )
}

export const Bone = { Text, Number, Chip, Block, Dot, Ring }

/**
 * One Region per streamed section (its Suspense fallback), never per component:
 * a screen reader hears "Loading the papers" once, not forty grey rectangles,
 * and the scan sweep crosses the section as a single line. `status` is the
 * already-translated sentence — this shared module cannot call useT/getT.
 */
function Region({
  status,
  className,
  children,
  ...props
}: { status: string; children?: ReactNode } & ComponentPropsWithoutRef<'div'>) {
  return (
    <div {...props} data-skeleton="" aria-busy="true" className={clsx('relative', className)}>
      <span role="status" className="sr-only">
        {status}
      </span>
      <div aria-hidden="true">{children}</div>
    </div>
  )
}

export const Skeleton = { Region }

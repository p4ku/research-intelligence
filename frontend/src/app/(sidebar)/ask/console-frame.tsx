import clsx from 'clsx'
import type { FormEventHandler, ReactNode } from 'react'

/**
 * The Ask console's static chrome, shared by the live console (ask.tsx) and
 * its skeleton (skeletons.tsx). No directive and no hooks: this module renders
 * on the server for loading.tsx and inside the client tree for the console.
 * Elements that carry refs or motion stay in ask.tsx and take their classes
 * from the constants here, so the two cannot drift.
 */

export const RAISED =
  'shadow-[0_1px_2px_rgba(19,19,17,0.05),0_5px_14px_-4px_rgba(19,19,17,0.10)] dark:shadow-none'

/** The console body: transcript above, the dock below. */
export const BODY_CLASS = 'relative flex min-h-0 flex-1 flex-col'
/** Before the first question the dock sits a third of the way down. */
export const EMPTY_BODY_PAD = 'pt-[clamp(2rem,10vh,7rem)]'
export const GREETING_WRAP = 'mx-auto mb-[18px] w-[min(100%-3rem,800px)] shrink-0'
export const DOCK_WRAP = 'relative z-[4] mx-auto w-[min(100%-3rem,800px)] shrink-0 pb-5'
/** The composer field's box; the textarea adds its colours and focus reset. */
export const FIELD_CLASS =
  'block max-h-44 w-full resize-none bg-transparent px-4 pt-3.5 pb-1.5 text-[15px] leading-relaxed'

/**
 * Console left, history right; on mobile the history folds into a <details>
 * under the console. minmax(0,…) on the mobile column too: the implicit auto
 * track sized itself to the history rows' min-content and pushed the page
 * wider than the viewport (pre-existing; surfaced by the touch-target work).
 */
export function AskLayout({
  console,
  railLabel,
  rail,
  mobileTitle,
  mobileCount,
  mobileList,
  after,
}: {
  console: ReactNode
  railLabel: string
  rail: ReactNode
  mobileTitle: ReactNode
  mobileCount: ReactNode
  mobileList: ReactNode
  /** Anything outside the panes — the delete dialog. */
  after?: ReactNode
}) {
  return (
    <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)] grid-rows-[minmax(0,1fr)_auto] gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(17rem,1fr)] lg:grid-rows-1">
      {console}

      {/* History rail: always to the right. */}
      <aside aria-label={railLabel} className="min-h-0 overflow-y-auto pb-6 max-lg:hidden">
        {rail}
      </aside>

      <details className="rounded-sm border border-line bg-surface px-4 py-3 lg:hidden">
        <summary className="cursor-default text-xs font-semibold tracking-[0.18em] text-foreground uppercase">
          {mobileTitle}{' '}
          <span className="font-mono font-normal text-muted-foreground normal-case tabular-nums">
            · {mobileCount}
          </span>
        </summary>
        <div className="mt-3 max-h-72 overflow-y-auto">{mobileList}</div>
      </details>

      {after}
    </div>
  )
}

/** The console card and its strip: the mono eyebrow left, the target (or a note) right. */
export function ConsoleFrame({
  label,
  eyebrow,
  aside,
  children,
}: {
  label: string
  eyebrow: ReactNode
  aside: ReactNode
  children: ReactNode
}) {
  return (
    <section
      aria-label={label}
      className={clsx(
        'relative isolate flex min-h-0 min-w-0 flex-col rounded-sm border border-line-strong bg-surface',
        RAISED,
      )}
    >
      <div className="flex shrink-0 items-center gap-3 border-b border-line-soft px-4 py-2.5">
        <span className="font-mono text-[11px] font-medium tracking-[0.18em] text-foreground uppercase">
          {eyebrow}
        </span>
        <div className="ml-auto flex min-w-0 items-center">{aside}</div>
      </div>
      {children}
    </section>
  )
}

/** The strip's quiet right-hand note ("No paper yet"). */
export function ConsoleNote({ children }: { children: ReactNode }) {
  return (
    <span className="font-mono text-[10px] tracking-[0.07em] text-muted-foreground uppercase">
      {children}
    </span>
  )
}

/** The empty console's one-line welcome, above the dock. */
export function Greeting({ lead }: { lead: ReactNode }) {
  return <p className="text-[15px] text-balance text-foreground">{lead}</p>
}

/** The composer box: the field on top, the chip/send row under it. */
export function ComposerFrame({
  onSubmit,
  field,
  footer,
}: {
  onSubmit?: FormEventHandler<HTMLFormElement>
  field: ReactNode
  footer: ReactNode
}) {
  return (
    <form
      onSubmit={onSubmit}
      className="relative flex flex-col rounded-sm border border-line bg-surface transition focus-within:border-accent/60 focus-within:ring-4 focus-within:ring-accent/15"
    >
      {field}
      <div className="flex min-h-10 items-center gap-2 py-1.5 pr-2 pb-2 pl-3">{footer}</div>
    </form>
  )
}

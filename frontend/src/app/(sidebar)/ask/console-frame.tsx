import clsx from 'clsx'
import type { FormEventHandler, ReactNode } from 'react'

/**
 * The Ask canvas's static chrome, shared by the live console (ask.tsx) and
 * its skeleton (skeletons.tsx). No directive and no hooks: this module renders
 * on the server for loading.tsx and inside the client tree for the console.
 * Elements that carry refs or motion stay in ask.tsx and take their classes
 * from the constants here, so the two cannot drift.
 *
 * The canvas is the page: no card-in-card, no eyebrow strip, no history
 * column. A top bar, a conversation, a docked composer — everything else the
 * assistant can do arrives through the composer's tool menu.
 */

export const RAISED =
  'shadow-[0_1px_2px_rgba(19,19,17,0.05),0_5px_14px_-4px_rgba(19,19,17,0.10)] dark:shadow-none'

/** The canvas body: conversation above, the dock below. */
export const BODY_CLASS =
  'relative flex min-h-0 flex-1 flex-col transition-[padding] duration-[260ms] ease-out motion-reduce:transition-none'
/**
 * From `md` up the open sidecar pushes the conversation instead of covering
 * it — at these widths the measure plus the panel do not both fit, and a
 * panel over the send button is worse than one short reflow on toggle.
 * Below `md` the panel is a full-width drawer, so nothing needs to move.
 */
export const BODY_PUSHED = 'md:pr-[17rem]'
/** Before the first question the greeting and dock sit centred, ChatGPT-style. */
export const EMPTY_BODY = 'justify-center pb-[10vh]'
export const GREETING_WRAP = 'mx-auto mb-5 w-[min(100%-3rem,768px)] shrink-0'
export const DOCK_WRAP = 'relative z-[4] mx-auto w-[min(100%-3rem,768px)] shrink-0 pb-4'
/** The composer field's box; the textarea adds its colours and focus reset. */
export const FIELD_CLASS =
  'block max-h-44 w-full resize-none bg-transparent px-1.5 py-[7px] text-[15px] leading-relaxed'
/** The top bar's height, which the sidecar hangs below. */
export const TOP_BAR_H = '3.25rem'

/** A glyph for "open the panel on the right" — heroicons has no panel icon. */
export function PanelRightIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      aria-hidden="true"
      className={className}
    >
      <path
        d="M4.5 5.25h15a1.5 1.5 0 0 1 1.5 1.5v10.5a1.5 1.5 0 0 1-1.5 1.5h-15a1.5 1.5 0 0 1-1.5-1.5V6.75a1.5 1.5 0 0 1 1.5-1.5ZM15 5.25v13.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/**
 * The canvas: one surface that owns the viewport. `overflow-hidden` is what
 * lets the sidecar park off the right edge without widening the page.
 */
export function AskCanvas({
  label,
  top,
  children,
  sidecar,
}: {
  label: string
  top: ReactNode
  children: ReactNode
  /** The recent-chats panel, which positions itself against this element. */
  sidecar?: ReactNode
}) {
  return (
    <section
      aria-label={label}
      className={clsx(
        'border-line bg-surface relative isolate flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-sm border',
        RAISED,
      )}
    >
      {top}
      {children}
      {sidecar}
    </section>
  )
}

/** The top bar: the thread's name left, the two chrome actions right. */
export function TopBar({ title, actions }: { title: ReactNode; actions: ReactNode }) {
  return (
    <header className="flex shrink-0 items-center gap-3 px-3 py-2.5" style={{ height: TOP_BAR_H }}>
      <h2 className="text-foreground min-w-0 flex-1 truncate text-[15px] font-semibold tracking-tight">
        {title}
      </h2>
      <div className="flex shrink-0 items-center gap-0.5">{actions}</div>
    </header>
  )
}

/**
 * The top bar's quiet icon buttons, and the tool menu's trigger. Both "held
 * open" states are covered: `data-open` is ours (the sidecar toggle), and
 * `data-state=open` is Radix's on a dropdown trigger.
 */
export const ICON_BUTTON =
  'text-muted-foreground hover:bg-foreground/5 hover:text-foreground focus-visible:outline-accent data-open:bg-foreground/5 data-open:text-foreground data-[state=open]:bg-foreground/5 data-[state=open]:text-foreground grid size-8 shrink-0 place-items-center rounded-sm transition-colors duration-150 ease-out focus-visible:outline-2 focus-visible:outline-offset-2 disabled:pointer-events-none disabled:opacity-40'

/** The empty canvas's one-line welcome, above the dock. */
export function Greeting({ lead }: { lead: ReactNode }) {
  return (
    <p className="text-foreground text-center text-[26px] leading-tight font-medium tracking-[-0.02em] text-balance">
      {lead}
    </p>
  )
}

/**
 * The composer box: an attachment row when a paper is scoped, then the one
 * row that matters — tools, field, send.
 */
export function ComposerFrame({
  onSubmit,
  attachment,
  leading,
  field,
  trailing,
}: {
  onSubmit?: FormEventHandler<HTMLFormElement>
  /** The scoped paper's chip, above the field like an attachment. */
  attachment?: ReactNode
  /** The tool menu's trigger. */
  leading: ReactNode
  field: ReactNode
  /** Send / stop. */
  trailing: ReactNode
}) {
  return (
    <form
      onSubmit={onSubmit}
      className="border-line bg-surface focus-within:border-accent/60 focus-within:ring-accent/15 relative flex flex-col rounded-sm border transition focus-within:ring-4"
    >
      {attachment && <div className="px-2 pt-2">{attachment}</div>}
      <div className="flex items-end gap-1.5 p-1.5">
        {leading}
        {field}
        {trailing}
      </div>
    </form>
  )
}

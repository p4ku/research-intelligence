'use client'

import { SectionLabel } from '@/components/scanner-ui'
import { Bone, Skeleton } from '@/components/skeleton'
import { Spinner } from '@/components/ui/spinner'
import type { ChatSession } from '@/lib/bff/chat/schema'
import { fmt, formatNumber } from '@/lib/i18n'
import { useLanguage, useT } from '@/lib/i18n-client'
import { TrashIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import type { ReactNode } from 'react'
import { TOP_BAR_H } from './console-frame'
import { shortTitle, timeOf } from './types'

/** 'Today', 'Yesterday', or a short local date — the sidecar's group label. */
function dayLabel(iso: string, lang: string, t: (s: string) => string): string {
  const date = new Date(iso)
  const today = new Date()
  const startOf = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const days = Math.round((startOf(today) - startOf(date)) / 86_400_000)
  if (days <= 0) return t('Today')
  if (days === 1) return t('Yesterday')
  return date.toLocaleDateString(lang === 'de' ? 'de-DE' : 'en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  })
}

/* ---------------------------------- Frames --------------------------------- */

// Separated from the open target by a divider; on touch it is visible at
// rest and grows real padding to a ~44px target (a positioned ::after
// overhang widened the page on mobile — don't reintroduce).
const TRASH =
  'text-muted-foreground hover:text-negative border-line-soft ml-1 flex items-center self-stretch border-l py-1 pr-1 pl-2 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 pointer-coarse:py-4 pointer-coarse:pr-3.5 pointer-coarse:pl-4 pointer-coarse:opacity-100'

function DayLabel({ day, count }: { day: ReactNode; count: ReactNode }) {
  return (
    <p
      data-row="day"
      className="sticky top-0 z-10 flex items-baseline bg-surface px-2 py-1 font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase"
    >
      {day}
      <span className="ml-auto tabular-nums">{count}</span>
    </p>
  )
}

/** A session row: the scope spine, the open target, the delete affordance. */
function HistoryRowFrame({
  active = false,
  busy = false,
  spine,
  body,
  trash,
}: {
  active?: boolean
  busy?: boolean
  /** The spine's colour class. */
  spine: string
  body: ReactNode
  trash: ReactNode
}) {
  return (
    <div
      data-row="session"
      aria-busy={busy || undefined}
      className={clsx(
        'group flex w-full items-stretch gap-2 rounded-sm px-1.5 py-1.5',
        // The panel is already on the surface, so the open row reads by
        // tint, not by a card — a white-on-white card would vanish here.
        active ? 'bg-foreground/6' : 'hover:bg-foreground/4',
      )}
    >
      <span aria-hidden="true" className={clsx('w-[3px] shrink-0 rounded-full', spine)} />
      {body}
      {trash}
    </div>
  )
}

function RowBody({
  active = false,
  title,
  meta,
}: {
  active?: boolean
  title: ReactNode
  meta: ReactNode
}) {
  return (
    <>
      <span
        className={clsx(
          'block text-[13px] leading-snug',
          active ? 'font-medium text-foreground' : 'text-muted-foreground',
        )}
      >
        {title}
      </span>
      <span className="mt-1 flex min-w-0 items-center gap-1.5 font-mono text-[10px] text-muted-foreground tabular-nums">
        {meta}
      </span>
    </>
  )
}

/* ---------------------------------- Loaded --------------------------------- */

function HistoryRow({
  session,
  active,
  opening,
  onOpen,
  onDelete,
}: {
  session: ChatSession
  active: boolean
  opening: boolean
  onOpen: () => void
  onDelete: () => void
}) {
  const t = useT()
  return (
    <HistoryRowFrame
      active={active}
      busy={opening}
      // Scope spine: accent for a single paper, neutral for the whole corpus.
      spine={session.paper_id ? 'bg-accent/70' : 'bg-line-strong'}
      body={
        <button
          type="button"
          onClick={onOpen}
          aria-current={active || undefined}
          className="min-w-0 flex-1 text-left"
        >
          <RowBody
            active={active}
            title={<span className="line-clamp-2 block">{session.title}</span>}
            // 17rem of room: the time and the scope, nothing else. The
            // question count lives in the sidecar's header.
            meta={
              <>
                {opening && <Spinner aria-hidden="true" className="size-3 shrink-0" />}
                {active && <span className="size-1.5 shrink-0 rounded-full bg-accent" />}
                <span className="shrink-0">{timeOf(session.updated_at)}</span>
                <span aria-hidden="true">·</span>
                {session.paper_title ? (
                  <span className="truncate">{shortTitle(session.paper_title)}</span>
                ) : (
                  <span className="truncate">{t('All papers')}</span>
                )}
              </>
            }
          />
        </button>
      }
      trash={
        <button
          type="button"
          onClick={onDelete}
          title={t('Delete conversation')}
          aria-label={t('Delete conversation')}
          className={TRASH}
        >
          <TrashIcon className="size-3.5" />
        </button>
      }
    />
  )
}

export function HistoryList({
  threads,
  activeId,
  openingId = null,
  rowError = null,
  onOpen,
  onDelete,
}: {
  threads: ChatSession[]
  activeId: string | null
  openingId?: string | null
  rowError?: { id: string; message: string } | null
  onOpen: (session: ChatSession) => void
  onDelete: (session: ChatSession) => void
}) {
  const t = useT()
  const { lang } = useLanguage()
  // Group by day, preserving order (sessions arrive newest first).
  const groups: { day: string; items: ChatSession[] }[] = []
  for (const session of threads) {
    const day = dayLabel(session.updated_at, lang, t)
    const last = groups[groups.length - 1]
    if (last?.day === day) last.items.push(session)
    else groups.push({ day, items: [session] })
  }

  if (threads.length === 0) {
    return (
      <p className="px-3 py-6 text-center text-xs text-balance text-muted-foreground">
        {t('Questions you ask are filed here.')}
      </p>
    )
  }

  return (
    <div className="space-y-4">
      {groups.map((g) => (
        <div key={g.day}>
          <DayLabel day={g.day} count={g.items.length} />
          <div className="mt-0.5 space-y-0.5">
            {g.items.map((session) => (
              <div key={session.id}>
                <HistoryRow
                  session={session}
                  active={session.id === activeId}
                  opening={session.id === openingId}
                  onOpen={() => onOpen(session)}
                  onDelete={() => onDelete(session)}
                />
                {rowError?.id === session.id && (
                  <p role="alert" className="px-2 pt-1 pb-0.5 text-[11px] text-negative">
                    {rowError.message}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

/** The sidecar's shared shell, so the skeleton cannot drift from the panel. */
function SidecarFrame({
  open,
  label,
  count,
  children,
}: {
  open: boolean
  label: string
  count: ReactNode
  children: ReactNode
}) {
  return (
    <aside
      aria-label={label}
      data-shape="history-sidecar"
      data-open={open || undefined}
      // Closed, the panel is parked off the right edge — `inert` keeps its
      // rows out of the tab order and off the accessibility tree while the
      // transform still has something to animate.
      inert={!open}
      // The panel overlays the conversation, so it stops at the dock's top
      // edge: covering the composer would put the send and stop buttons out of
      // reach at exactly the moment you want them (`--dock-h`, set in ask.tsx).
      style={{ top: TOP_BAR_H, bottom: 'var(--dock-top, 6rem)' }}
      className="absolute right-0 left-0 z-10 flex translate-x-full flex-col border-l border-line-soft bg-surface transition-transform duration-[260ms] ease-out will-change-transform motion-reduce:transition-none md:left-auto md:w-[17rem] data-open:translate-x-0 data-open:shadow-[-12px_0_28px_-22px_rgba(19,19,17,0.5)]"
    >
      <div className="flex items-baseline gap-2 px-3 pt-3.5 pb-1">
        <SectionLabel className="!text-[11px]">{label}</SectionLabel>
        <span className="ml-auto shrink-0 font-mono text-[11px] text-muted-foreground tabular-nums">
          {count}
        </span>
      </div>
      {children}
    </aside>
  )
}

/**
 * Recent chats: hidden by default, slid in from the top bar's panel button.
 * It rides over the canvas's right gutter rather than taking a column, so
 * opening it never reflows a conversation mid-stream. Reopening a thread
 * loads it settled — you are re-reading a filed conversation, not replaying it.
 */
export function HistorySidecar({
  open,
  threads,
  activeId,
  openingId = null,
  rowError = null,
  loading = false,
  stale = false,
  onRefresh,
  onOpen,
  onDelete,
}: {
  open: boolean
  threads: ChatSession[]
  activeId: string | null
  openingId?: string | null
  rowError?: { id: string; message: string } | null
  /** The history has not arrived yet (it loads after the console paints). */
  loading?: boolean
  stale?: boolean
  onRefresh?: () => void
  onOpen: (session: ChatSession) => void
  onDelete: (session: ChatSession) => void
}) {
  const t = useT()
  const { lang } = useLanguage()
  if (loading) {
    return (
      <SidecarFrame open={open} label={t('Recent')} count={<Bone.Text widths={['11ch']} />}>
        <Skeleton.Region
          status={t('Loading recent chats')}
          className="min-h-0 flex-1"
          innerClassName="h-full overflow-y-auto px-1.5 pb-4"
        >
          <HistoryBones groups={[2, 3]} lines={[1, 2]} />
        </Skeleton.Region>
      </SidecarFrame>
    )
  }
  return (
    <SidecarFrame
      open={open}
      label={t('Recent')}
      count={
        threads.length === 1
          ? t('1 question')
          : fmt(t('{n} questions'), { n: formatNumber(threads.length, lang) })
      }
    >
      {stale && (
        <p role="status" className="px-3 pb-1 text-[11px] text-muted-foreground">
          {t('History may be out of date.')}{' '}
          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              className="font-medium text-foreground hover:underline"
            >
              {t('Refresh')}
            </button>
          )}
        </p>
      )}
      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-4">
        <HistoryList
          threads={threads}
          activeId={activeId}
          openingId={openingId}
          rowError={rowError}
          onOpen={onOpen}
          onDelete={onDelete}
        />
      </div>
    </SidecarFrame>
  )
}

/* --------------------------------- Skeleton -------------------------------- */

/**
 * The list's bones. `groups` is the row count per day label; `lines` cycles
 * the title height per row (questions wrap to two lines about half the
 * time). The live sidecar shows these until the history lands; the gallery
 * passes the fixture's shape.
 */
function HistoryBones({ groups, lines }: { groups: number[]; lines: number[] }) {
  return (
    <div className="space-y-4">
      {groups.map((count, g) => {
        const before = groups.slice(0, g).reduce((a, b) => a + b, 0)
        return (
          <div key={g}>
            <DayLabel day={<Bone.Text widths={['6ch']} />} count={<Bone.Number digits={1} />} />
            <div className="mt-0.5 space-y-0.5">
              {Array.from({ length: count }, (_, i) => (
                <HistoryRowFrame
                  key={i}
                  spine="bg-foreground/8"
                  body={
                    <div className="min-w-0 flex-1 text-left">
                      <RowBody
                        title={
                          <Bone.Text
                            lines={lines[(before + i) % lines.length]}
                            widths={['100%', '64%']}
                          />
                        }
                        meta={<Bone.Text widths={['16ch']} />}
                      />
                    </div>
                  }
                  trash={
                    <span className={clsx(TRASH, 'invisible')}>
                      <TrashIcon className="size-3.5" />
                    </span>
                  }
                />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/** The whole sidecar as bones — the gallery's before-shot. */
export function HistorySidecarSkeleton({
  open = true,
  groups = [2, 4],
  lines = [1, 2],
}: {
  open?: boolean
  groups?: number[]
  lines?: number[]
}) {
  const t = useT()
  return (
    <SidecarFrame open={open} label={t('Recent')} count={<Bone.Text widths={['11ch']} />}>
      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-4">
        <HistoryBones groups={groups} lines={lines} />
      </div>
    </SidecarFrame>
  )
}

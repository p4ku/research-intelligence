'use client'

import { SectionLabel } from '@/components/scanner-ui'
import { Bone } from '@/components/skeleton'
import { Spinner } from '@/components/ui/spinner'
import type { ChatSession } from '@/lib/bff/chat/schema'
import { fmt } from '@/lib/i18n'
import { useLanguage, useT } from '@/lib/i18n-client'
import { PlusIcon, TrashIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import type { ReactNode } from 'react'
import { shortTitle, timeOf } from './types'

/** 'Today', 'Yesterday', or a short local date — the rail's group label. */
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

const NEW_BUTTON =
  'border-line bg-surface text-foreground hover:border-line-strong hover:bg-foreground/5 focus-visible:outline-accent mt-2.5 flex w-full items-center justify-center gap-1.5 rounded-sm border px-3 py-2 text-xs font-medium whitespace-nowrap transition-[background-color,border-color,transform] duration-150 ease-out focus-visible:outline-2 focus-visible:outline-offset-2 active:scale-[0.99]'

// Separated from the open target by a divider; on touch it is visible at
// rest and grows real padding to a ~44px target (a positioned ::after
// overhang widened the page on mobile — don't reintroduce).
const TRASH =
  'text-muted-foreground hover:text-negative border-line-soft ml-1 flex items-center self-stretch border-l py-1 pr-1 pl-2 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 pointer-coarse:py-4 pointer-coarse:pr-3.5 pointer-coarse:pl-4 pointer-coarse:opacity-100'

function RailHeader({
  label,
  count,
  action,
}: {
  label: ReactNode
  count: ReactNode
  action: ReactNode
}) {
  // Two rows, not one: the label/count line and the action line each own
  // their width, so neither the count nor the button label can wrap when
  // the rail narrows. Mirrors the day-group headers below.
  return (
    <div className="px-3">
      <div className="flex items-baseline gap-2">
        <SectionLabel className="!text-[11px]">{label}</SectionLabel>
        <span className="ml-auto shrink-0 font-mono text-[11px] text-muted-foreground tabular-nums">
          {count}
        </span>
      </div>
      {action}
    </div>
  )
}

function DayLabel({ day, count }: { day: ReactNode; count: ReactNode }) {
  return (
    <p
      data-row="day"
      className="sticky top-0 z-10 flex items-baseline bg-background px-3 py-1 font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase"
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
        'group flex w-full items-stretch gap-2.5 rounded-sm py-2 pr-2 pl-2',
        active ? 'border border-line bg-surface shadow-xs' : 'hover:bg-foreground/5',
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
          'block text-xs',
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
                <span aria-hidden="true">·</span>
                <span className="shrink-0">
                  {session.turns_count === 1
                    ? t('1 question')
                    : fmt(t('{n} questions'), { n: session.turns_count })}
                </span>
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
      <p className="px-3 py-6 text-center text-xs text-muted-foreground">
        {t('Questions you ask are filed here.')}
      </p>
    )
  }

  return (
    <div className="space-y-5">
      {groups.map((g) => (
        <div key={g.day}>
          <DayLabel day={g.day} count={g.items.length} />
          <div className="mt-1 space-y-0.5">
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

/**
 * The history rail: past sessions filed by day on the shell grey; only the
 * open one gets a surface. Reopening loads the thread settled — you are
 * re-reading a filed conversation, not replaying it.
 */
export function HistoryRail({
  threads,
  activeId,
  openingId = null,
  rowError = null,
  stale = false,
  onRefresh,
  onOpen,
  onNew,
  onDelete,
}: {
  threads: ChatSession[]
  activeId: string | null
  openingId?: string | null
  rowError?: { id: string; message: string } | null
  stale?: boolean
  onRefresh?: () => void
  onOpen: (session: ChatSession) => void
  onNew: () => void
  onDelete: (session: ChatSession) => void
}) {
  const t = useT()
  return (
    <div data-shape="history-rail" data-state="loaded">
      <RailHeader
        label={t('History')}
        count={
          threads.length === 1 ? t('1 question') : fmt(t('{n} questions'), { n: threads.length })
        }
        action={
          <button type="button" onClick={onNew} className={NEW_BUTTON}>
            <PlusIcon className="size-3.5 shrink-0" />
            {t('New conversation')}
          </button>
        }
      />
      {stale && (
        <p role="status" className="mt-2 px-3 text-[11px] text-muted-foreground">
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
      <div className="mt-3">
        <HistoryList
          threads={threads}
          activeId={activeId}
          openingId={openingId}
          rowError={rowError}
          onOpen={onOpen}
          onDelete={onDelete}
        />
      </div>
    </div>
  )
}

/* --------------------------------- Skeleton -------------------------------- */

/**
 * The rail's bones. `groups` is the row count per day label; `lines` cycles
 * the title height per row (questions wrap to two lines about half the time).
 * The gallery passes the fixture's shape; loading.tsx a generic one.
 */
export function HistoryRailSkeleton({
  groups = [6],
  lines = [1, 2],
}: {
  groups?: number[]
  lines?: number[]
}) {
  const t = useT()
  return (
    <div data-shape="history-rail" data-state="skeleton">
      <RailHeader
        label={t('History')}
        count={<Bone.Text widths={['11ch']} />}
        action={
          <span className={NEW_BUTTON}>
            <PlusIcon className="size-3.5 shrink-0" />
            {t('New conversation')}
          </span>
        }
      />
      <div className="mt-3">
        <div className="space-y-5">
          {groups.map((count, g) => {
            const before = groups.slice(0, g).reduce((a, b) => a + b, 0)
            return (
              <div key={g}>
                <DayLabel day={<Bone.Text widths={['6ch']} />} count={<Bone.Number digits={1} />} />
                <div className="mt-1 space-y-0.5">
                  {Array.from({ length: count }, (_, i) => (
                    <div key={i}>
                      <HistoryRowFrame
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
                              meta={<Bone.Text widths={['22ch']} />}
                            />
                          </div>
                        }
                        trash={
                          <span className={clsx(TRASH, 'invisible')}>
                            <TrashIcon className="size-3.5" />
                          </span>
                        }
                      />
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

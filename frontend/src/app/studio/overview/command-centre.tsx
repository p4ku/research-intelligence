'use client'

/**
 * The overview's controller: owns the view state (scope, open run, filter,
 * drill-down level), mirrors it to the URL, fetches steps and editions for
 * the open run, polls while a run is active, and moves focus and the
 * announcer when the open run changes. Layout is CSS: all three panes are
 * always in the DOM, `data-level` decides which one the phone shows.
 *
 * Nothing here reads the viewport during render — the server does not know
 * it. `matchMedia` is consulted in event handlers only.
 */
import type { Edition } from '@/lib/bff/briefings/schema'
import { BffClientError, bffFetch } from '@/lib/bff/client'
import type { ComponentRun } from '@/lib/bff/component-runs/schema'
import type { Page } from '@/lib/bff/core/pagination'
import type { PipelineRun, RunsOverview } from '@/lib/bff/pipeline-runs/schema'
import { problemMessage } from '@/lib/bff/problem-copy'
import type { WorkspaceSummary } from '@/lib/bff/workspaces/schema'
import clsx from 'clsx'
import { usePathname } from 'next/navigation'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { shortId } from '../run-presentation'
import { Crumbs } from './crumbs'
import {
  notices as deriveNotices,
  fmtUtc,
  indexRuns,
  isTestWorkspace,
  railOrder,
  scopeRuns,
  summariseWorkspace,
} from './derive'
import { DetailPane } from './detail-pane'
import { IDLE, type Loadable } from './loadable'
import { MONO, STATUS_LABEL } from './primitives'
import { Rail } from './rail'
import { RunList } from './run-list'
import { announcementFor, reduce, toSearch, type OverviewAction, type OverviewState } from './state'
import { useActivePolling } from './use-active-polling'

const NARROW = '(max-width: 1023.98px)'
const identity = (s: string) => s

function isNarrow(): boolean {
  return typeof window !== 'undefined' && window.matchMedia(NARROW).matches
}

export interface CommandCentreProps {
  runs: PipelineRun[]
  workspaces: WorkspaceSummary[]
  truncated: boolean
  initial: OverviewState
  /** When the server rendered this: the first "Last updated" and the clock for relative ages. */
  renderedAt: string
  /** The reading app's workspace (sidebar cookie), for the briefing link. */
  currentWorkspaceId: string | null
  /** A one-line note when the URL asked for something the data does not have. */
  note: string | null
}

export function CommandCentre({
  runs: initialRuns,
  workspaces: initialWorkspaces,
  truncated: initialTruncated,
  initial,
  renderedAt,
  currentWorkspaceId,
  note,
}: CommandCentreProps) {
  const pathname = usePathname()
  const [data, setData] = useState({
    runs: initialRuns,
    workspaces: initialWorkspaces,
    truncated: initialTruncated,
  })
  const index = useMemo(() => indexRuns(data.runs), [data.runs])
  const [now, setNow] = useState(renderedAt)
  const [updatedAt, setUpdatedAt] = useState(renderedAt)
  const [refreshError, setRefreshError] = useState<string | null>(null)

  // Transitions go through `send`, which computes the next state with the
  // current index and clock, stores it, and announces a changed open run —
  // once, from the state diff, whatever handler caused it.
  const ctxRef = useRef({ index, nowIso: now })
  ctxRef.current = { index, nowIso: now }
  const [state, setState] = useState(initial)
  const stateRef = useRef(state)
  const [announcement, setAnnouncement] = useState<{ text: string; key: number }>({
    text: '',
    key: 0,
  })
  const retained = useRef(new Map<string, PipelineRun>())

  const describe = useCallback((runId: string) => {
    const run = ctxRef.current.index.byId.get(runId) ?? retained.current.get(runId)
    if (!run) return `Run ${shortId(runId)} opened.`
    return `Run ${shortId(runId)}, ${STATUS_LABEL[run.status]}, ${run.workspace_name}, ${
      run.status === 'pending' ? 'queued' : 'started'
    } ${run.started_at ? fmtUtc(run.started_at) : 'at an unknown time'}.`
  }, [])

  const send = useCallback(
    (action: OverviewAction) => {
      const prev = stateRef.current
      const next = reduce(prev, action, ctxRef.current)
      if (next === prev) return
      stateRef.current = next
      setState(next)
      const text = announcementFor(prev, next, describe)
      if (text) setAnnouncement((a) => ({ text, key: a.key + 1 }))
    },
    [describe],
  )

  /* ------------------------------ derived ------------------------------ */
  const todayYmd = now.slice(0, 10)
  const summaries = useMemo(
    () => new Map(data.workspaces.map((ws) => [ws.id, summariseWorkspace(ws, index, todayYmd)])),
    [data.workspaces, index, todayYmd],
  )
  const orderedWorkspaces = useMemo(
    () => railOrder(data.workspaces, summaries),
    [data.workspaces, summaries],
  )
  const wsById = useMemo(() => new Map(data.workspaces.map((ws) => [ws.id, ws])), [data.workspaces])
  const scopeWs = state.scope === 'all' ? null : (wsById.get(state.scope) ?? null)
  const scoped = scopeRuns(index, state.scope)
  const scopeNotices = useMemo(() => {
    const all = deriveNotices(data.workspaces, summaries)
    return state.scope === 'all' ? all : all.filter((n) => n.workspace.id === state.scope)
  }, [data.workspaces, summaries, state.scope])
  const realRuns = useMemo(
    () => index.all.filter((r) => !isTestWorkspace({ name: r.workspace_name })),
    [index],
  )
  const allSummary = useMemo(
    () => ({
      runs: index.all.length,
      live: index.all.filter((r) => r.status === 'running').length,
      anyBad: realRuns.some((r) => r.status === 'failed' || r.status === 'aborted'),
      usdUsed: data.workspaces.reduce((sum, ws) => sum + ws.usd_spent, 0),
    }),
    [index, realRuns, data.workspaces],
  )

  // The open run: from the live index, or the object we last had if the
  // refresh no longer lists it.
  const liveRun = state.runId ? index.byId.get(state.runId) : undefined
  if (liveRun) retained.current.set(liveRun.id, liveRun)
  const openRun = liveRun ?? (state.runId ? retained.current.get(state.runId) : undefined) ?? null
  const stale = Boolean(state.runId && !liveRun && openRun)

  /* ------------------------------ on demand ----------------------------- */
  const [stepsById, setStepsById] = useState<Record<string, Loadable<ComponentRun[]>>>({})
  const [editionById, setEditionById] = useState<Record<string, Loadable<Edition | null>>>({})
  const inFlight = useRef(new Set<string>())

  const loadSteps = useCallback(async (runId: string, force = false) => {
    const key = `steps:${runId}`
    if (inFlight.current.has(key)) return
    inFlight.current.add(key)
    try {
      const page = await bffFetch<Page<ComponentRun>>(
        `/bff/component-runs?pipeline_run_id=${runId}&page_size=200`,
      )
      setStepsById((prev) => ({ ...prev, [runId]: { status: 'ready', data: page.results } }))
    } catch (error) {
      if (error instanceof BffClientError && error.problem.status === 404) {
        setStepsById((prev) => ({ ...prev, [runId]: { status: 'ready', data: [] } }))
      } else {
        const message =
          error instanceof BffClientError
            ? problemMessage(error.problem, identity)
            : problemMessage(null, identity)
        setStepsById((prev) =>
          force && prev[runId]?.status === 'ready'
            ? prev
            : { ...prev, [runId]: { status: 'error', message } },
        )
      }
    } finally {
      inFlight.current.delete(key)
    }
  }, [])

  const loadEdition = useCallback(async (runId: string) => {
    const key = `edition:${runId}`
    if (inFlight.current.has(key)) return
    inFlight.current.add(key)
    try {
      const found = await bffFetch<Edition>(`/bff/pipeline-runs/${runId}/edition`)
      setEditionById((prev) => ({ ...prev, [runId]: { status: 'ready', data: found } }))
    } catch (error) {
      if (error instanceof BffClientError && error.problem.status === 404) {
        setEditionById((prev) => ({ ...prev, [runId]: { status: 'ready', data: null } }))
      } else {
        const message =
          error instanceof BffClientError
            ? problemMessage(error.problem, identity)
            : problemMessage(null, identity)
        setEditionById((prev) => ({ ...prev, [runId]: { status: 'error', message } }))
      }
    } finally {
      inFlight.current.delete(key)
    }
  }, [])

  // Fetch what the open run needs, once per run. State updates happen after
  // the fetch resolves, so an absent entry reads as "loading".
  const openId = openRun?.id ?? null
  const openStatus = openRun?.status ?? null
  useEffect(() => {
    if (!openId) return
    if (!stepsById[openId]) void loadSteps(openId)
    if (openStatus === 'completed' && !editionById[openId]) void loadEdition(openId)
  }, [openId, openStatus, stepsById, editionById, loadSteps, loadEdition])

  /* ------------------------------- polling ------------------------------ */
  const active =
    index.all.some((r) => r.status === 'running' || r.status === 'pending') ||
    openStatus === 'running' ||
    openStatus === 'pending'

  const openRef = useRef<{ id: string | null; status: string | null }>({
    id: openId,
    status: openStatus,
  })
  openRef.current = { id: openId, status: openStatus }

  useActivePolling({
    active,
    onTick: async () => {
      try {
        const fresh = await bffFetch<RunsOverview>('/bff/pipeline-runs/overview')
        const before = openRef.current
        setData({ runs: fresh.runs, workspaces: fresh.workspaces, truncated: fresh.truncated })
        setUpdatedAt(fresh.generated_at)
        setNow(fresh.generated_at)
        setRefreshError(null)
        if (before.id) {
          const after = fresh.runs.find((r) => r.id === before.id)
          const wasActive = before.status === 'running' || before.status === 'pending'
          if (wasActive) {
            void loadSteps(before.id, true)
            if (after && after.status === 'completed') {
              setEditionById((prev) => {
                const next = { ...prev }
                delete next[before.id as string]
                return next
              })
            }
          }
        }
        return true
      } catch (error) {
        const message =
          error instanceof BffClientError
            ? problemMessage(error.problem, identity)
            : problemMessage(null, identity)
        setRefreshError(message)
        // A 401 is already on its way to the logout page; stop retrying.
        if (error instanceof BffClientError && error.problem.status === 401) return true
        return false
      }
    },
  })

  // Relative ages move even between polls, but only while something runs.
  useEffect(() => {
    if (!active) return
    const timer = setInterval(() => setNow(new Date().toISOString()), 60_000)
    return () => clearInterval(timer)
  }, [active])

  /* ------------------------------ URL mirror ---------------------------- */
  const firstRender = useRef(true)
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    const url = `${pathname}${toSearch(state)}`
    if (`${window.location.pathname}${window.location.search}` !== url) {
      window.history.replaceState(window.history.state, '', url)
    }
  }, [pathname, state])

  /* ------------------------- focus and announcer ------------------------ */
  const rowRefs = useRef(new Map<string, HTMLButtonElement>())
  const titleRef = useRef<HTMLHeadingElement>(null)
  const lastTrigger = useRef<string | null>(null)

  const rowRef = useCallback((id: string, el: HTMLButtonElement | null) => {
    if (el) rowRefs.current.set(id, el)
    else rowRefs.current.delete(id)
  }, [])

  const focusRow = (id: string | null) => {
    const el = (id && rowRefs.current.get(id)) || rowRefs.current.values().next().value
    el?.focus()
  }

  const onOpen = (id: string) => {
    const narrow = isNarrow()
    lastTrigger.current = id
    send({ type: 'open', id, narrow })
    if (narrow) {
      window.scrollTo(0, 0)
      requestAnimationFrame(() => titleRef.current?.focus())
    }
  }
  const onClose = () => {
    const back = lastTrigger.current
    lastTrigger.current = null
    send({ type: 'close' })
    requestAnimationFrame(() => focusRow(back))
  }
  const onScope = (id: string) => {
    const narrow = isNarrow()
    send({ type: 'scope', id, narrow })
    if (narrow) window.scrollTo(0, 0)
    else
      requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-ws="${id}"]`)?.focus())
  }
  const onFilter = (filter: OverviewState['filter']) =>
    send({ type: 'filter', filter, narrow: isNarrow() })
  const onLevel = (level: OverviewState['level']) => {
    send({ type: 'level', level })
    window.scrollTo(0, 0)
    requestAnimationFrame(() => {
      if (level === 'list') focusRow(stateRef.current.runId)
      else if (level === 'rail')
        document.querySelector<HTMLElement>(`[data-ws="${stateRef.current.scope}"]`)?.focus()
    })
  }

  // Escape closes the pane while one is open.
  useEffect(() => {
    if (!state.runId) return
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key !== 'Escape') return
      const target = ev.target as HTMLElement | null
      if (target && /^(input|textarea|select)$/i.test(target.tagName)) return
      onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
    // onClose is stable enough: it only dispatches and moves focus.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.runId])

  // Growing past `lg` with nothing open: the pane takes the default run.
  useEffect(() => {
    const mq = window.matchMedia(NARROW)
    const onChange = () => {
      if (!mq.matches) send({ type: 'widen' })
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [send])

  /* -------------------------------- render ------------------------------ */
  const scopeName = scopeWs ? scopeWs.name : 'All workspaces'
  const open = Boolean(openRun)
  const level = state.level

  return (
    <div
      data-level={level}
      data-open={open ? 'true' : 'false'}
      className="lg:grid lg:h-[calc(100dvh-6rem)] lg:min-h-0 lg:grid-rows-[auto_minmax(0,1fr)]"
    >
      {/* ------------------------------ header ------------------------------ */}
      <div className="border-line flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b pb-3 max-lg:mb-0 lg:pb-2.5">
        <h1 className="text-[22px] leading-7 font-semibold tracking-tight">Overview</h1>
        <p className="text-muted-foreground text-xs">
          Every run across your workspaces. Scope here is this page&apos;s; the sidebar workspace is
          unchanged.
        </p>
        <p className={clsx(MONO, 'text-muted-foreground ml-auto text-[11.5px] max-sm:w-full')}>
          Last updated <b className="text-foreground font-medium">{fmtUtc(updatedAt)}</b>
          {refreshError && <span className="text-negative"> · refresh failed: {refreshError}</span>}
        </p>
        {note && <p className="text-warn-ink w-full text-xs">{note}</p>}
      </div>

      <p key={announcement.key} className="sr-only" aria-live="polite" aria-atomic="true">
        {announcement.text}
      </p>

      <Crumbs level={level} scopeName={scopeName} runId={openRun?.id ?? null} onLevel={onLevel} />

      <div
        className={clsx(
          'wide:grid-rows-[minmax(0,1fr)] lg:max-wide:grid-rows-[auto_minmax(0,1fr)] lg:grid lg:min-h-0',
          open
            ? 'wide:grid-cols-[208px_minmax(0,1fr)_400px] lg:max-wide:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]'
            : 'wide:grid-cols-[208px_minmax(0,1fr)] lg:max-wide:grid-cols-[minmax(0,1fr)]',
        )}
      >
        <aside
          className={clsx(
            'bg-surface border-line wide:overflow-y-auto wide:overscroll-contain wide:border-r lg:max-wide:col-span-full lg:max-wide:border-b lg:min-h-0',
            level !== 'rail' && 'max-lg:hidden',
          )}
        >
          <Rail
            workspaces={orderedWorkspaces}
            summaries={summaries}
            all={allSummary}
            scope={state.scope}
            onScope={onScope}
          />
        </aside>

        <section
          aria-label="Runs"
          className={clsx(
            'bg-background lg:min-h-0 lg:overflow-y-auto lg:overscroll-contain',
            open && 'lg:border-line lg:border-r',
            level !== 'list' && 'max-lg:hidden',
          )}
        >
          <RunList
            scope={state.scope}
            workspace={scopeWs}
            runs={scoped}
            index={index}
            summary={scopeWs ? (summaries.get(scopeWs.id) ?? null) : null}
            notices={scopeNotices}
            workspaceCount={data.workspaces.length}
            filter={state.filter}
            runId={openRun?.id ?? null}
            now={now}
            truncated={data.truncated}
            onFilter={onFilter}
            onOpen={onOpen}
            onScope={onScope}
            rowRef={rowRef}
          />
        </section>

        <section
          id="run-detail"
          role="region"
          aria-label="Run detail"
          aria-live="polite"
          className={clsx(
            'bg-surface lg:min-h-0 lg:overflow-y-auto lg:overscroll-contain',
            level !== 'detail' && 'max-lg:hidden',
            !open && 'hidden',
          )}
        >
          {openRun && (
            <div aria-live="off">
              <DetailPane
                ref={titleRef}
                run={openRun}
                workspace={wsById.get(openRun.workspace_id)}
                index={index}
                steps={stepsById[openRun.id] ?? { status: 'loading' }}
                edition={editionById[openRun.id] ?? IDLE}
                now={now}
                stale={stale}
                currentWorkspaceId={currentWorkspaceId}
                onClose={onClose}
                onScope={onScope}
              />
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

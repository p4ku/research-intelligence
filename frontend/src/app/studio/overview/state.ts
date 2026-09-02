/**
 * The overview's view state and its transitions, pure so the scope, filter
 * and close semantics can be tested without React. `narrow` is passed in by
 * the caller from a media query at event time — never read during render —
 * so the same reducer serves the three-pane and the drill-down layouts.
 */
import {
  defaultRun,
  reconcileFilter,
  scopeRuns,
  statusCounts,
  type Filter,
  type RunIndex,
} from './derive'

export type Level = 'rail' | 'list' | 'detail'

export interface OverviewState {
  /** `all` or a workspace id. */
  scope: string
  runId: string | null
  filter: Filter
  /** Which pane the drill-down shows below `lg`; ignored by wider layouts. */
  level: Level
}

export type OverviewAction =
  | { type: 'scope'; id: string; narrow: boolean }
  | { type: 'open'; id: string; narrow: boolean }
  | { type: 'close' }
  | { type: 'filter'; filter: Filter; narrow: boolean }
  | { type: 'level'; level: Level }
  /** The layout grew past `lg` with nothing open: the pane takes the default run. */
  | { type: 'widen' }

export interface ReducerContext {
  index: RunIndex
  nowIso: string
}

export function reduce(
  state: OverviewState,
  action: OverviewAction,
  ctx: ReducerContext,
): OverviewState {
  switch (action.type) {
    case 'scope': {
      const scoped = scopeRuns(ctx.index, action.id)
      const filter = reconcileFilter(state.filter, statusCounts(scoped))
      const open = state.runId ? ctx.index.byId.get(state.runId) : undefined
      const stillInScope = open && (action.id === 'all' || open.workspace_id === action.id)
      const runId = stillInScope
        ? state.runId
        : action.narrow
          ? null
          : defaultRun(filtered(scoped, filter), ctx.nowIso)
      return { scope: action.id, filter, runId, level: 'list' }
    }
    case 'open': {
      // On a wide layout a second click on the open row closes the pane.
      const runId = state.runId === action.id && !action.narrow ? null : action.id
      return { ...state, runId, level: runId ? 'detail' : 'list' }
    }
    case 'close':
      return { ...state, runId: null, level: state.level === 'detail' ? 'list' : state.level }
    case 'filter': {
      const open = state.runId ? ctx.index.byId.get(state.runId) : undefined
      const scoped = scopeRuns(ctx.index, state.scope)
      const keep =
        action.narrow || action.filter === 'all' || !open || open.status === action.filter
      const runId = keep ? state.runId : defaultRun(filtered(scoped, action.filter), ctx.nowIso)
      return { ...state, filter: action.filter, runId }
    }
    case 'level':
      return { ...state, level: action.level }
    case 'widen':
      return state.runId
        ? state
        : {
            ...state,
            runId: defaultRun(
              filtered(scopeRuns(ctx.index, state.scope), state.filter),
              ctx.nowIso,
            ),
          }
  }
}

function filtered<T extends { status: string }>(runs: T[], filter: Filter): T[] {
  return filter === 'all' ? runs : runs.filter((r) => r.status === filter)
}

/** The query string that reproduces this state; empty at the defaults. */
export function toSearch(state: OverviewState): string {
  const params = new URLSearchParams()
  if (state.scope !== 'all') params.set('ws', state.scope)
  if (state.runId) params.set('run', state.runId)
  if (state.filter !== 'all') params.set('status', state.filter)
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

/** What the announcer says when the open run changes; null when it did not. */
export function announcementFor(
  prev: OverviewState,
  next: OverviewState,
  describe: (runId: string) => string,
): string | null {
  if (prev.runId === next.runId) return null
  return next.runId ? describe(next.runId) : 'Run detail closed.'
}

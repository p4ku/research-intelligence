/**
 * Everything the Studio overview derives from runs and workspaces, as pure
 * functions: what each workspace's state is, which run the pane opens on,
 * how the list groups and orders, which stage a run is in. No React, no
 * server imports — derive.test.ts exercises all of it on the fixtures.
 *
 * Two honesty rules live here and nowhere else:
 *  - `PipelineRun.current_stage` is the last stage the engine *dispatched*
 *    and a rerun rewrites it (pipeline-runs/schema.ts), so it only ever
 *    lights a segment for a run that is `running`. A failed or aborted run's
 *    bad stage comes from its failed component run, or is not shown.
 *  - Absent is not zero: a run without a start time sorts last, a workspace
 *    without a limit has no percentage.
 */
import type { ComponentRun } from '@/lib/bff/component-runs/schema'
import {
  STAGES,
  stageLabel,
  type PipelineRun,
  type RunStatus,
  type Stage,
} from '@/lib/bff/pipeline-runs/schema'
import type { WorkspaceSummary } from '@/lib/bff/workspaces/schema'
import { formatDuration } from '../run-presentation'

export type Filter = 'all' | RunStatus

/** Attention first, then queued, then the calm majority. */
export const STATUS_ORDER: RunStatus[] = ['running', 'failed', 'aborted', 'pending', 'completed']
const ATTENTION = new Set<RunStatus>(['running', 'failed', 'aborted'])
const BAD = new Set<RunStatus>(['failed', 'aborted'])

/** A failed run older than this no longer claims the pane by default. */
export const ATTENTION_WINDOW_MS = 7 * 24 * 3600 * 1000

/** The e2e suite leaves these on prod; they are shown, but last and muted. */
export function isTestWorkspace(ws: Pick<WorkspaceSummary, 'name'>): boolean {
  return /^test_e2e_/i.test(ws.name)
}

export function isAttention(status: RunStatus): boolean {
  return ATTENTION.has(status)
}

/* --------------------------------- Index --------------------------------- */

export interface RunIndex {
  /** Newest first. */
  all: PipelineRun[]
  byId: Map<string, PipelineRun>
  byWorkspace: Map<string, PipelineRun[]>
  /** Newest started (not queued) run per workspace. */
  newestInWorkspace: Map<string, string>
  /** Newest started run per workspace and day (`workspace|run_date`). */
  newestInDay: Map<string, string>
  dayCount: Map<string, number>
}

function startedMs(run: PipelineRun): number {
  return run.started_at ? Date.parse(run.started_at) : Number.NEGATIVE_INFINITY
}

/** Newest first; runs without a start time last; ties broken by id for stability. */
export function newestFirst(a: PipelineRun, b: PipelineRun): number {
  return startedMs(b) - startedMs(a) || a.id.localeCompare(b.id)
}

export function dayKey(run: PipelineRun): string {
  return `${run.workspace_id}|${run.run_date}`
}

export function indexRuns(runs: PipelineRun[]): RunIndex {
  const all = [...runs].sort(newestFirst)
  const byId = new Map<string, PipelineRun>()
  const byWorkspace = new Map<string, PipelineRun[]>()
  const newestInWorkspace = new Map<string, string>()
  const newestInDay = new Map<string, string>()
  const dayCount = new Map<string, number>()
  for (const run of all) {
    byId.set(run.id, run)
    const list = byWorkspace.get(run.workspace_id) ?? []
    list.push(run)
    byWorkspace.set(run.workspace_id, list)
    const key = dayKey(run)
    dayCount.set(key, (dayCount.get(key) ?? 0) + 1)
    // A queued run has not started, so it never holds a "latest" mark.
    if (run.status === 'pending') continue
    if (!newestInWorkspace.has(run.workspace_id)) newestInWorkspace.set(run.workspace_id, run.id)
    if (!newestInDay.has(key)) newestInDay.set(key, run.id)
  }
  return { all, byId, byWorkspace, newestInWorkspace, newestInDay, dayCount }
}

export function scopeRuns(index: RunIndex, scope: string): PipelineRun[] {
  return scope === 'all' ? index.all : (index.byWorkspace.get(scope) ?? [])
}

/* ------------------------------- Workspaces ------------------------------- */

export type WorkspaceState = 'none' | 'running' | 'attention' | 'ok'

export interface WorkspaceSummaryDerived {
  runs: PipelineRun[]
  state: WorkspaceState
  live: number
  bad: number
  queued: number
  /** Percent of the USD limit used; null when the workspace has no limit. */
  usdPct: number | null
  tokPct: number | null
  /** Sum of the listed runs' recorded costs. */
  runCost: number
}

export function quotaPercent(used: number, limit: number | null): number | null {
  if (limit === null || limit <= 0) return null
  return (used / limit) * 100
}

export function costOfRuns(runs: PipelineRun[]): number {
  return runs.reduce((sum, r) => sum + (Number.isFinite(r.usd_cost) ? r.usd_cost : 0), 0)
}

export function summariseWorkspace(
  ws: WorkspaceSummary,
  index: RunIndex,
  todayYmd: string,
): WorkspaceSummaryDerived {
  const runs = index.byWorkspace.get(ws.id) ?? []
  const live = runs.filter((r) => r.status === 'running').length
  const bad = runs.filter((r) => BAD.has(r.status)).length
  const queued = runs.filter((r) => r.status === 'pending').length
  const newestId = index.newestInWorkspace.get(ws.id)
  const newest = newestId ? index.byId.get(newestId) : undefined
  const badToday = runs.some((r) => BAD.has(r.status) && r.run_date === todayYmd)
  const state: WorkspaceState =
    runs.length === 0
      ? 'none'
      : live
        ? 'running'
        : (newest && BAD.has(newest.status)) || badToday
          ? 'attention'
          : 'ok'
  return {
    runs,
    state,
    live,
    bad,
    queued,
    usdPct: quotaPercent(ws.usd_spent, ws.monthly_usd_limit),
    tokPct: quotaPercent(ws.tokens_consumed, ws.monthly_token_limit),
    runCost: costOfRuns(runs),
  }
}

const STATE_RANK: Record<WorkspaceState, number> = { running: 0, attention: 1, ok: 2, none: 3 }

/** Rail order: what needs eyes first, test workspaces last, names to break ties. */
export function railOrder(
  workspaces: WorkspaceSummary[],
  summaries: Map<string, WorkspaceSummaryDerived>,
): WorkspaceSummary[] {
  return [...workspaces].sort((a, b) => {
    const testDiff = Number(isTestWorkspace(a)) - Number(isTestWorkspace(b))
    if (testDiff) return testDiff
    const ra = STATE_RANK[summaries.get(a.id)?.state ?? 'none']
    const rb = STATE_RANK[summaries.get(b.id)?.state ?? 'none']
    return ra - rb || a.name.localeCompare(b.name)
  })
}

export type Notice =
  | { kind: 'budget'; workspace: WorkspaceSummary; pct: number }
  | { kind: 'no-runs'; workspace: WorkspaceSummary }

export const BUDGET_WARN_PCT = 80

/** Workspace-level notices for the attention section; test workspaces never raise one. */
export function notices(
  workspaces: WorkspaceSummary[],
  summaries: Map<string, WorkspaceSummaryDerived>,
): Notice[] {
  const out: Notice[] = []
  for (const ws of workspaces) {
    if (isTestWorkspace(ws)) continue
    const s = summaries.get(ws.id)
    if (!s) continue
    if (s.usdPct !== null && s.usdPct >= BUDGET_WARN_PCT) {
      out.push({ kind: 'budget', workspace: ws, pct: s.usdPct })
    }
    if (s.runs.length === 0) out.push({ kind: 'no-runs', workspace: ws })
  }
  return out
}

/* ---------------------------------- Runs ---------------------------------- */

/**
 * The run the pane opens on: a running run, else a run that failed or was
 * aborted within the attention window, else the newest run. Test
 * workspaces' runs never claim the pane on their own.
 */
export function defaultRun(runs: PipelineRun[], nowIso: string): string | null {
  const now = Date.parse(nowIso)
  const running = runs.find((r) => r.status === 'running')
  if (running) return running.id
  const recentBad = runs.find((r) => {
    if (!BAD.has(r.status)) return false
    const when = Date.parse(r.completed_at ?? r.started_at ?? '')
    return Number.isFinite(when) && now - when <= ATTENTION_WINDOW_MS
  })
  if (recentBad) return recentBad.id
  return runs[0]?.id ?? null
}

/** Running, then failed, then aborted; newest first within each. */
export function attentionRuns(runs: PipelineRun[]): PipelineRun[] {
  return runs
    .filter((r) => ATTENTION.has(r.status))
    .sort(
      (a, b) =>
        STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) || newestFirst(a, b),
    )
}

export interface DayGroup {
  date: string
  runs: PipelineRun[]
}

/** Days newest first; rows newest first within a day, whichever workspace they belong to. */
export function groupByDay(runs: PipelineRun[]): DayGroup[] {
  const byDate = new Map<string, PipelineRun[]>()
  for (const run of runs) {
    const list = byDate.get(run.run_date) ?? []
    list.push(run)
    byDate.set(run.run_date, list)
  }
  return [...byDate.entries()]
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([date, rows]) => ({ date, runs: [...rows].sort(newestFirst) }))
}

export function statusCounts(runs: PipelineRun[]): Partial<Record<RunStatus, number>> {
  const counts: Partial<Record<RunStatus, number>> = {}
  for (const run of runs) counts[run.status] = (counts[run.status] ?? 0) + 1
  return counts
}

/** A status filter survives a scope change only if the new scope has that status. */
export function reconcileFilter(
  filter: Filter,
  counts: Partial<Record<RunStatus, number>>,
): Filter {
  return filter === 'all' || (counts[filter] ?? 0) > 0 ? filter : 'all'
}

export function triggerText(run: PipelineRun): string {
  if (run.schedule_name) return `Schedule · ${run.schedule_name}`
  if (run.schedule_id) return 'Schedule'
  if (run.triggered_by) return `Manual · ${run.triggered_by}`
  return 'Manual'
}

/** "Latest in workspace" / "Latest that day" (only when the day has several) / "Reprocessed". */
export function runMarks(run: PipelineRun, index: RunIndex): string[] {
  const marks: string[] = []
  const key = dayKey(run)
  if (run.status !== 'pending') {
    if (index.newestInWorkspace.get(run.workspace_id) === run.id) marks.push('Latest in workspace')
    else if (index.newestInDay.get(key) === run.id && (index.dayCount.get(key) ?? 0) > 1) {
      marks.push('Latest that day')
    }
  }
  if (run.reprocess_existing) marks.push('Reprocessed')
  return marks
}

/* --------------------------------- Stages --------------------------------- */

const STAGE_SET = new Set<string>(STAGES)

export function asStage(value: string | null): Stage | null {
  return value && STAGE_SET.has(value) ? (value as Stage) : null
}

/** The overview stage a component run belongs to; null for steps the strip does not draw. */
export function stageForStep(
  step: Pick<ComponentRun, 'step_type' | 'component_name'>,
): Stage | null {
  switch (step.step_type) {
    case 'screening':
      return /full/i.test(step.component_name) ? 'full_text_screening' : 'abstract_screening'
    case 'search':
    case 'download':
    case 'ocr':
    case 'extraction':
    case 'signal_score':
    case 'reporting':
      return step.step_type
    default:
      return null
  }
}

/**
 * Where a run stopped, as evidence allows: a failed or aborted run's bad
 * step; a running run's dispatched stage. Null for everything else — a
 * completed run's `current_stage` says nothing about where it "stopped".
 */
export function stoppedStage(run: PipelineRun, steps: ComponentRun[] | null): Stage | null {
  if (BAD.has(run.status)) {
    const bad = steps?.find((s) => s.status === 'failed' || s.status === 'aborted')
    return bad ? stageForStep(bad) : null
  }
  if (run.status === 'running') return asStage(run.current_stage)
  return null
}

export type SegmentTone = 'idle' | 'done' | 'now' | 'bad'

/**
 * One tone per stage. With steps, each stage takes the tone of its step
 * (evidence). Without, a running run lights everything before its dispatched
 * stage as done — the engine reached it — and nothing for any other status.
 */
export function segmentTones(run: PipelineRun, steps: ComponentRun[] | null): SegmentTone[] {
  const tones: SegmentTone[] = STAGES.map(() => 'idle')
  if (steps && steps.length) {
    for (const step of steps) {
      const stage = stageForStep(step)
      if (!stage) continue
      const i = STAGES.indexOf(stage)
      if (step.status === 'completed' || step.status === 'skipped') tones[i] = 'done'
      else if (step.status === 'running') tones[i] = 'now'
      else if (step.status === 'failed' || step.status === 'aborted') tones[i] = 'bad'
    }
    return tones
  }
  if (run.status === 'running') {
    const stage = asStage(run.current_stage)
    if (stage) {
      const at = STAGES.indexOf(stage)
      for (let i = 0; i < at; i++) tones[i] = 'done'
      tones[at] = 'now'
    }
  }
  return tones
}

/** The sentence under the segments, and what a screen reader hears instead of them. */
export function stageSentence(
  run: PipelineRun,
  steps: ComponentRun[] | null,
  nowIso: string,
): string {
  const n = STAGES.length
  if (run.status === 'running') {
    const live = steps?.find((s) => s.status === 'running')
    const stage = live ? stageForStep(live) : asStage(run.current_stage)
    const label = stage ? stageLabel(stage) : stageLabel(run.current_stage ?? 'search')
    const at = stage ? `, stage ${STAGES.indexOf(stage) + 1} of ${n}` : ''
    const since = live?.started_at ?? run.started_at
    const clock = since
      ? ` · ${live ? 'step' : 'run'} started ${fmtClockUtc(since)} UTC, ${relativeAge(since, nowIso)}`
      : ''
    return `${label}${at}${clock}`
  }
  if (run.status === 'pending') {
    return `Queued at ${stageLabel(run.current_stage ?? 'search')} · nothing dispatched yet`
  }
  if (BAD.has(run.status)) {
    const stage = stoppedStage(run, steps)
    if (stage) return `Stopped in ${stageLabel(stage)}, stage ${STAGES.indexOf(stage) + 1} of ${n}`
    return run.current_stage
      ? `Last stage dispatched · ${stageLabel(run.current_stage)}`
      : 'No stage recorded'
  }
  return 'Completed'
}

/* ---------------------------------- Time ---------------------------------- */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

function p2(n: number): string {
  return String(n).padStart(2, '0')
}

/** `2 Sep 2026, 09:15 UTC` — fixed to UTC so server and browser agree. */
export function fmtUtc(iso: string): string {
  const t = new Date(iso)
  if (Number.isNaN(t.getTime())) return '—'
  return `${t.getUTCDate()} ${MONTHS[t.getUTCMonth()]} ${t.getUTCFullYear()}, ${p2(t.getUTCHours())}:${p2(t.getUTCMinutes())} UTC`
}

/** `09:15` */
export function fmtClockUtc(iso: string): string {
  const t = new Date(iso)
  if (Number.isNaN(t.getTime())) return '—'
  return `${p2(t.getUTCHours())}:${p2(t.getUTCMinutes())}`
}

/** `2 Sep 2026` from a YYYY-MM-DD. */
export function fmtDate(ymd: string): string {
  const t = new Date(`${ymd}T00:00:00Z`)
  if (Number.isNaN(t.getTime())) return ymd
  return `${t.getUTCDate()} ${MONTHS[t.getUTCMonth()]} ${t.getUTCFullYear()}`
}

/** `Wed 2 Sep 2026` from a YYYY-MM-DD. */
export function fmtDay(ymd: string): string {
  const t = new Date(`${ymd}T00:00:00Z`)
  if (Number.isNaN(t.getTime())) return ymd
  return `${DAYS[t.getUTCDay()]} ${fmtDate(ymd)}`
}

/** `4m ago`, against the clock the caller passes — never Date.now() in render. */
export function relativeAge(iso: string, nowIso: string): string {
  const s = (Date.parse(nowIso) - Date.parse(iso)) / 1000
  if (!Number.isFinite(s)) return '—'
  if (s < 0) return 'just now'
  if (s < 60) return `${Math.round(s)}s ago`
  if (s < 3600) return `${Math.round(s / 60)}m ago`
  if (s < 86400) return `${Math.round(s / 3600)}h ago`
  return `${Math.round(s / 86400)}d ago`
}

/** How long a run has been going, against the caller's clock. */
export function elapsed(startedIso: string, nowIso: string): string {
  return formatDuration(Math.max(0, (Date.parse(nowIso) - Date.parse(startedIso)) / 1000))
}

export function plural(n: number, word: string): string {
  return n === 1 ? word : `${word}s`
}

export function percentOf(part: number, whole: number): number | null {
  return whole > 0 ? Math.round((part / whole) * 100) : null
}

/** The day a run's edition is filed under (briefings/service.ts `editionDate`). */
export function editionDateOf(run: PipelineRun): string {
  return run.completed_at ? run.completed_at.slice(0, 10) : run.run_date
}

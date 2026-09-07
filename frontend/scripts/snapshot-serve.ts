#!/usr/bin/env bun
/**
 * Replay a `snapshot:pull` capture as a stand-in Django on :8010. Point the
 * app at it with BACKEND_INTERNAL_URL=http://localhost:8010 — nothing in the
 * app changes; the real proxy, BFF and mappers run against real data.
 *
 * - GET  → the captured `index.json` for that path, with `?workspace=`,
 *          `?paper=`, `?status=` (any `key=value`) applied to list responses.
 * - POST /api/auth/login/ and /refresh/ → dev-signed JWTs with a real `exp`
 *          (the proxy only reads `exp`; rotation is mirrored like production).
 * - POST /api/pipeline-runs/start/ → a simulated run: `running` at the top
 *          of the list at once, `completed` (or `failed`, see env) after
 *          SNAPSHOT_RUN_MS. In memory only; restart to forget it.
 * - GET/PUT /api/stars/ → an in-memory star set (ids must exist in the
 *          capture, as Django would 404). Restart to forget.
 * - Anything else that writes → 501, in Django's error shape.
 *
 * Env: SNAPSHOT_DIR (default: newest folder under local-data/), SNAPSHOT_PORT
 * (default 8010), SNAPSHOT_RUN_MS (default 8000), SNAPSHOT_RUN_OUTCOME
 * (`completed` | `failed`).
 */
import { createHmac, randomUUID } from 'node:crypto'
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { createServer, type IncomingMessage, type ServerResponse } from 'node:http'
import { join } from 'node:path'

const ROOT = join(import.meta.dir, '..', 'local-data')
const PORT = Number(process.env.SNAPSHOT_PORT ?? 8010)
const DIR = process.env.SNAPSHOT_DIR ?? newestSnapshot()
const SECRET = 'snapshot-dev-secret'
const RUN_MS = Number(process.env.SNAPSHOT_RUN_MS ?? 8000)
const RUN_OUTCOME = process.env.SNAPSHOT_RUN_OUTCOME === 'failed' ? 'failed' : 'completed'

function newestSnapshot(): string {
  if (!existsSync(ROOT)) fail(`No ${ROOT}. Run \`bun run snapshot:pull\` first.`)
  const dirs = readdirSync(ROOT)
    .map((d) => join(ROOT, d))
    .filter((d) => existsSync(join(d, 'manifest.json')))
    .sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs)
  if (dirs.length === 0) fail(`No snapshots in ${ROOT}. Run \`bun run snapshot:pull\` first.`)
  return dirs[0]
}

function fail(message: string): never {
  console.error(message)
  process.exit(2)
}

function base64url(input: string | Buffer): string {
  return Buffer.from(input).toString('base64url')
}

/** HS256 JWT. Not for security — the app only decodes `exp` from it. */
function jwt(type: 'access' | 'refresh', ttlSeconds: number): string {
  const now = Math.floor(Date.now() / 1000)
  const head = base64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = base64url(
    JSON.stringify({
      token_type: type,
      exp: now + ttlSeconds,
      iat: now,
      jti: randomUUID().replace(/-/g, ''),
      user_id: '1',
    }),
  )
  const sig = createHmac('sha256', SECRET).update(`${head}.${body}`).digest('base64url')
  return `${head}.${body}.${sig}`
}

function tokenPair() {
  return { access: jwt('access', 60 * 60), refresh: jwt('refresh', 60 * 60 * 24) }
}

function load(pathname: string): unknown | undefined {
  const file = join(DIR, pathname.replace(/^\/|\/$/g, ''), 'index.json')
  if (!existsSync(file)) return undefined
  return JSON.parse(readFileSync(file, 'utf8')) as unknown
}

/** Django-style `?field=value` filtering on a captured list. */
function filterRows(rows: unknown[], query: URLSearchParams): unknown[] {
  const skip = new Set(['ordering', 'page', 'page_size', 'search'])
  return rows.filter((row) => {
    if (!row || typeof row !== 'object') return true
    const r = row as Record<string, unknown>
    for (const [key, value] of query) {
      if (skip.has(key)) continue
      const actual = r[key] ?? r[`${key}_id`]
      if (actual === undefined || actual === null) return false
      if (String(actual) !== value) return false
    }
    return true
  })
}

type Row = Record<string, unknown>

/** Runs started through the replay, newest first; served ahead of the capture. */
const startedRuns: Row[] = []

/** The replay user's stars, the shape of Django's /api/stars/. In memory only. */
const starred: { papers: string[]; briefings: string[] } = { papers: [], briefings: [] }

/** Ids the capture knows for a star kind, plus simulated runs for briefings. */
function knownIds(kind: 'paper' | 'briefing'): Set<string> {
  const body = load(kind === 'paper' ? '/api/papers/' : '/api/pipeline-runs/')
  const rows = Array.isArray(body)
    ? (body as Row[])
    : (((body as { results?: Row[] } | undefined)?.results ?? []) as Row[])
  const extra = kind === 'briefing' ? startedRuns : []
  return new Set([...rows, ...extra].map((r) => String(r.id)))
}

function readJson(req: IncomingMessage): Promise<unknown> {
  return new Promise((resolve) => {
    let text = ''
    req.setEncoding('utf8')
    req.on('data', (chunk: string) => (text += chunk))
    req.on('end', () => {
      try {
        resolve(text ? (JSON.parse(text) as unknown) : {})
      } catch {
        resolve({})
      }
    })
  })
}

function capturedRuns(): Row[] {
  const body = load('/api/pipeline-runs/')
  return Array.isArray(body) ? (body as Row[]) : []
}

/** A run in the list serializer's shape, modelled on the capture's first row. */
function simulateRun(
  ws: { id: string; name: string },
  input: { start_date?: string | null; end_date?: string | null; n_last_days?: number | null },
): Row {
  const now = new Date().toISOString()
  const template = capturedRuns()[0] ?? {}
  const cfg = {
    start_date: input.start_date ?? null,
    end_date: input.end_date ?? null,
    n_last_days: input.start_date || input.end_date ? null : (input.n_last_days ?? 7),
    autonomous: true,
  }
  return {
    ...template,
    id: randomUUID(),
    name: `Autonomous Pipeline Run - ${now.slice(0, 16).replace('T', ' ')}`,
    workspace: ws.id,
    workspace_name: ws.name,
    run_date: now.slice(0, 10),
    status: 'running',
    current_stage: 'search',
    configuration_override: cfg,
    period: cfg.start_date && cfg.end_date ? `${cfg.start_date} - ${cfg.end_date}` : null,
    total_papers_fetched: 0,
    total_papers_passed_screening: 0,
    tokens_in: 0,
    tokens_out: 0,
    tokens_consumed: 0,
    usd_cost: '0.0000',
    triggered_by: 1,
    triggered_by_username: 'admin',
    status_message: 'Searching sources.',
    started_at: now,
    completed_at: null,
    duration_seconds: null,
    execution_time_display: '⏱ running',
  }
}

/**
 * After RUN_MS: the outcome. A simulated run links no papers, so its
 * counters stay at zero — the composed briefing then reads as a quiet run
 * rather than claiming papers the corpus does not have.
 */
function finishRun(run: Row) {
  const now = new Date()
  const started = new Date(String(run.started_at))
  run.status = RUN_OUTCOME
  run.completed_at = now.toISOString()
  run.duration_seconds = (now.getTime() - started.getTime()) / 1000
  if (RUN_OUTCOME === 'completed') {
    run.current_stage = 'completed'
    run.status_message = 'Simulated run finished (snapshot replay): no papers.'
  } else {
    run.current_stage = 'abstract_screening'
    run.status_message = 'Simulated failure (SNAPSHOT_RUN_OUTCOME=failed).'
  }
}

function send(res: ServerResponse, status: number, body: unknown) {
  res.writeHead(status, { 'content-type': 'application/json' })
  res.end(JSON.stringify(body))
}

function djangoError(res: ServerResponse, status: number, error: string) {
  send(res, status, { status_code: status, error, detail: error })
}

const me = load('/api/auth/me/') ?? {
  id: 1,
  username: 'admin',
  email: '',
  full_name: 'admin',
  is_superuser: true,
  is_staff: true,
}

async function handle(req: IncomingMessage, res: ServerResponse) {
  const url = new URL(req.url ?? '/', `http://localhost:${PORT}`)
  const pathname = url.pathname.endsWith('/') ? url.pathname : `${url.pathname}/`
  const method = req.method ?? 'GET'
  const log = (status: number) => console.log(`${method} ${url.pathname}${url.search} → ${status}`)

  if (pathname === '/health/')
    return (log(200), send(res, 200, { status: 'ok', source: 'snapshot', dir: DIR }))
  if (method === 'POST' && pathname === '/api/auth/login/') {
    const u = me as { id?: number; username?: string }
    return (
      log(200),
      send(res, 200, {
        ...tokenPair(),
        user: me,
        user_id: u.id ?? 1,
        username: u.username ?? 'admin',
        workspace_id: null,
      })
    )
  }
  if (method === 'POST' && pathname === '/api/auth/refresh/')
    return (log(200), send(res, 200, tokenPair()))
  if (method === 'POST' && pathname === '/api/auth/logout/') return (log(200), send(res, 200, {}))
  if (method === 'POST' && pathname === '/api/pipeline-runs/start/') {
    const input = (await readJson(req)) as {
      workspace_id?: string
      start_date?: string | null
      end_date?: string | null
      n_last_days?: number | null
    }
    const workspaces = load('/api/workspaces/')
    const ws = (Array.isArray(workspaces) ? (workspaces as Row[]) : []).find(
      (w) => w.id === input.workspace_id,
    ) as { id: string; name: string } | undefined
    if (!ws) return (log(403), djangoError(res, 403, 'Access denied: not a workspace member.'))
    if (input.start_date && input.end_date && input.start_date > input.end_date)
      return (log(400), send(res, 400, { status: 'error', error: 'end_date precedes start_date' }))
    const run = simulateRun(ws, input)
    startedRuns.unshift(run)
    setTimeout(() => finishRun(run), RUN_MS)
    log(201)
    return send(res, 201, {
      status: 'success',
      pipeline_run_id: run.id,
      workspace_id: ws.id,
      run_status: 'running',
    })
  }
  if (pathname === '/api/stars/' && method === 'GET') return (log(200), send(res, 200, starred))
  if (pathname === '/api/stars/' && method === 'PUT') {
    const input = (await readJson(req)) as { kind?: unknown; id?: unknown; starred?: unknown }
    const kind = input.kind === 'paper' || input.kind === 'briefing' ? input.kind : null
    if (!kind || typeof input.id !== 'string' || typeof input.starred !== 'boolean')
      return (
        log(400),
        send(res, 400, { non_field_errors: ['kind, id and starred are required.'] })
      )
    if (!knownIds(kind).has(input.id))
      return (
        log(404),
        djangoError(res, 404, `${kind === 'paper' ? 'Paper' : 'Briefing'} not found.`)
      )
    const key = kind === 'paper' ? 'papers' : 'briefings'
    const rest = starred[key].filter((id) => id !== input.id)
    starred[key] = input.starred ? [...rest, input.id] : rest
    return (log(200), send(res, 200, starred))
  }
  if (method !== 'GET') return (log(501), djangoError(res, 501, 'Snapshot replay is read-only.'))

  let body = load(pathname)
  if (body === undefined) return (log(404), djangoError(res, 404, 'Not found.'))
  if (pathname === '/api/pipeline-runs/' && Array.isArray(body)) body = [...startedRuns, ...body]
  const out = Array.isArray(body) && url.search ? filterRows(body, url.searchParams) : body
  log(200)
  send(res, 200, out)
}

createServer(handle).listen(PORT, () => {
  console.log(`Snapshot backend on http://localhost:${PORT}  (${DIR})`)
  console.log(`  BACKEND_INTERNAL_URL=http://localhost:${PORT} bun run dev`)
})

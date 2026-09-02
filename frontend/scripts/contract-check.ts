#!/usr/bin/env bun
/**
 * Conformance check: does a live Django match the contract?
 *
 * - `current` operations are what the BFF calls today — any failure breaks
 *   the app now and fails the run (exit 1).
 * - `desired` operations are the endpoints we are asking the backend team to
 *   build — MISSING is expected until they exist; a desired endpoint that
 *   exists but MISMATCHes fails (that is the red/green loop to iterate on).
 *
 * Env: CONTRACT_BASE_URL (default http://localhost:8000), CONTRACT_USER
 * (default admin), CONTRACT_PASSWORD (default schwarz123!).
 * Flags: --only=<resource>  --json  --strict-desired
 */
import { allOperations } from '@/lib/bff/contract'
import type { Operation, ProbeParam } from '@/lib/bff/core/contract-types'
import * as z from 'zod'

const BASE = (process.env.CONTRACT_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')
const USER = process.env.CONTRACT_USER ?? 'admin'
const PASSWORD = process.env.CONTRACT_PASSWORD ?? 'schwarz123!'
const only = process.argv.find((a) => a.startsWith('--only='))?.slice(7)
const asJson = process.argv.includes('--json')
const strictDesired = process.argv.includes('--strict-desired')

type ResultKind = 'PASS' | 'MISSING' | 'MISMATCH' | 'ERROR' | 'SKIP'
interface Row {
  resource: string
  kind: Operation['kind']
  op: string
  result: ResultKind
  http: number | null
  note: string
}

async function getJson(path: string, token?: string): Promise<{ status: number; body: unknown }> {
  const res = await fetch(`${BASE}${path}`, {
    headers: token ? { authorization: `Bearer ${token}`, accept: 'application/json' } : {},
  })
  const text = await res.text()
  let body: unknown = text
  try {
    body = JSON.parse(text)
  } catch {
    /* keep text */
  }
  return { status: res.status, body }
}

async function login(): Promise<string> {
  const res = await fetch(`${BASE}/api/auth/login/`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username_or_email: USER, password: PASSWORD }),
  })
  const body = (await res.json().catch(() => null)) as { access?: string; error?: string } | null
  if (!res.ok || !body?.access) {
    console.error(
      `Login failed against ${BASE} as ${USER}: HTTP ${res.status} ${body?.error ?? ''}`,
    )
    process.exit(2)
  }
  return body.access
}

/** Sample ids for path templates, discovered from the current endpoints. */
async function discover(token: string): Promise<Partial<Record<ProbeParam, string>>> {
  const ctx: Partial<Record<ProbeParam, string>> = {}
  const ws = await getJson('/api/workspaces/', token)
  const workspaces = Array.isArray(ws.body) ? (ws.body as { id?: string }[]) : []
  if (workspaces[0]?.id) ctx.workspace_id = workspaces[0].id
  if (ctx.workspace_id) {
    const papers = await getJson('/api/papers/', token)
    const paper = Array.isArray(papers.body)
      ? (papers.body as { id?: string; workspace?: string }[]).find(
          (p) => p.workspace === ctx.workspace_id,
        )
      : undefined
    if (paper?.id) ctx.paper_id = paper.id
    const runs = await getJson(`/api/pipeline-runs/?workspace=${ctx.workspace_id}`, token)
    const run = Array.isArray(runs.body)
      ? (
          runs.body as {
            id?: string
            run_date?: string
            completed_at?: string | null
            status?: string
          }[]
        )[0]
      : undefined
    if (run?.id) ctx.run_id = run.id
    const completed = Array.isArray(runs.body)
      ? (runs.body as { run_date?: string; completed_at?: string | null; status?: string }[]).find(
          (r) => r.status === 'completed',
        )
      : undefined
    const date = completed?.completed_at?.slice(0, 10) ?? completed?.run_date
    if (date) ctx.date = date
    const sessions = await getJson(`/api/chat/sessions/?workspace_id=${ctx.workspace_id}`, token)
    const session = Array.isArray(sessions.body)
      ? (sessions.body as { id?: string }[])[0]
      : undefined
    if (session?.id) ctx.session_id = session.id
  }
  return ctx
}

function fillPath(op: Operation, ctx: Partial<Record<ProbeParam, string>>): string | null {
  let path = op.path
  for (const param of op.probe?.requires ?? []) {
    const value = ctx[param]
    if (!value) return null
    path = path.replaceAll(`{${param}}`, value)
  }
  return path.includes('{') ? null : path
}

/** Reach the object shape a response's items should have, for key diffing. */
function objectShape(schema: unknown): Record<string, unknown> | null {
  if (schema instanceof z.ZodObject) return schema.shape as Record<string, unknown>
  if (schema instanceof z.ZodArray) return objectShape(schema.element)
  if (schema instanceof z.ZodNullable || schema instanceof z.ZodOptional) {
    return objectShape(schema.unwrap())
  }
  return null
}

function sampleOf(body: unknown): Record<string, unknown> | null {
  if (Array.isArray(body)) return (body[0] as Record<string, unknown>) ?? null
  if (body && typeof body === 'object') {
    const record = body as Record<string, unknown>
    if (Array.isArray(record.results)) return (record.results[0] as Record<string, unknown>) ?? null
    return record
  }
  return null
}

function itemSchemaOf(schema: z.ZodType): unknown {
  const shape = schema instanceof z.ZodObject ? (schema.shape as Record<string, unknown>) : null
  if (shape && shape.results) return shape.results
  return schema
}

function extraKeys(schema: z.ZodType, body: unknown): string[] {
  const shape = objectShape(itemSchemaOf(schema))
  const sample = sampleOf(body)
  if (!shape || !sample) return []
  return Object.keys(sample).filter((k) => !(k in shape))
}

function issuesNote(error: z.ZodError): string {
  const issues = error.issues.slice(0, 4).map((issue) => {
    const path = issue.path.length ? issue.path.join('.') : '(root)'
    return `${path}: ${issue.message}`
  })
  const more = error.issues.length > 4 ? ` (+${error.issues.length - 4} more)` : ''
  return issues.join('; ') + more
}

async function checkOp(
  op: Operation,
  token: string,
  ctx: Partial<Record<ProbeParam, string>>,
): Promise<Row> {
  const base: Omit<Row, 'result' | 'http' | 'note'> = {
    resource: op.resource,
    kind: op.kind,
    op: `${op.method} ${op.path}`,
  }
  if (op.sse) return { ...base, result: 'SKIP', http: null, note: 'SSE — not executed' }
  if (op.method !== 'GET')
    return { ...base, result: 'SKIP', http: null, note: 'non-GET — not executed' }
  const path = fillPath(op, ctx)
  if (!path) return { ...base, result: 'SKIP', http: null, note: 'no sample id available' }
  let status: number
  let body: unknown
  try {
    ;({ status, body } = await getJson(path, token))
  } catch (error) {
    return { ...base, result: 'ERROR', http: null, note: `unreachable: ${String(error)}` }
  }
  if (status === 404 || status === 405)
    return { ...base, result: 'MISSING', http: status, note: '' }
  if (status >= 400)
    return { ...base, result: 'ERROR', http: status, note: JSON.stringify(body).slice(0, 120) }
  const schema = op.responses[200]
  if (!schema) return { ...base, result: 'PASS', http: status, note: 'no 200 schema declared' }
  const parsed = schema.safeParse(body)
  if (!parsed.success) {
    // An in-place upgrade that still answers in the old shape is not built
    // yet — that is MISSING, not a violation.
    if (op.supersedes) {
      const current = allOperations.find((o) => o.id === op.supersedes)
      if (current?.responses[200]?.safeParse(body).success) {
        return {
          ...base,
          result: 'MISSING',
          http: status,
          note: 'still the current shape — upgrade not built',
        }
      }
    }
    return { ...base, result: 'MISMATCH', http: status, note: issuesNote(parsed.error) }
  }
  const extras = extraKeys(schema, body)
  const note = extras.length > 0 ? `+extra: ${extras.slice(0, 6).join(', ')}` : ''
  return { ...base, result: 'PASS', http: status, note }
}

const COLORS: Record<ResultKind, string> = {
  PASS: '\x1b[32m',
  MISSING: '\x1b[33m',
  MISMATCH: '\x1b[31m',
  ERROR: '\x1b[31m',
  SKIP: '\x1b[2m',
}

function printTable(title: string, rows: Row[]) {
  if (rows.length === 0) return
  console.log(`\n${title}`)
  const opWidth = Math.max(...rows.map((r) => r.op.length), 10)
  for (const row of rows) {
    const color = COLORS[row.result]
    console.log(
      `  ${row.resource.padEnd(14)} ${row.op.padEnd(opWidth)}  ${color}${row.result.padEnd(8)}\x1b[0m ${
        row.http ?? '—'
      }  ${row.note}`,
    )
  }
}

const token = await login()
const ctx = await discover(token)
const ops = allOperations
  .filter((op) => op.face === 'django')
  .filter((op) => !only || op.resource === only)

const rows: Row[] = []
for (const op of ops) rows.push(await checkOp(op, token, ctx))

const current = rows.filter((r) => r.kind === 'current')
const desired = rows.filter((r) => r.kind === 'desired')

if (asJson) {
  console.log(JSON.stringify({ base: BASE, current, desired }, null, 2))
} else {
  console.log(`Contract check against ${BASE} (user: ${USER})`)
  printTable('Current endpoints (the BFF depends on these today):', current)
  printTable('Requested endpoints (MISSING is expected until built):', desired)
}

const currentBroken = current.filter((r) => r.result !== 'PASS' && r.result !== 'SKIP')
const desiredBroken = desired.filter(
  (r) => r.result === 'MISMATCH' || r.result === 'ERROR' || (strictDesired && r.result !== 'PASS'),
)
if (!asJson) {
  console.log(
    `\n${current.length - currentBroken.length}/${current.length} current OK · ` +
      `${desired.filter((r) => r.result === 'PASS').length}/${desired.length} requested built` +
      (currentBroken.length || desiredBroken.length ? '  → FAIL' : ''),
  )
}
process.exit(currentBroken.length > 0 || desiredBroken.length > 0 ? 1 : 0)

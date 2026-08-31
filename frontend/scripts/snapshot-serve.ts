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
 * - Anything else that writes → 501, in Django's error shape.
 *
 * Env: SNAPSHOT_DIR (default: newest folder under local-data/), SNAPSHOT_PORT
 * (default 8010).
 */
import { createHmac, randomUUID } from 'node:crypto'
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { createServer, type IncomingMessage, type ServerResponse } from 'node:http'
import { join } from 'node:path'

const ROOT = join(import.meta.dir, '..', 'local-data')
const PORT = Number(process.env.SNAPSHOT_PORT ?? 8010)
const DIR = process.env.SNAPSHOT_DIR ?? newestSnapshot()
const SECRET = 'snapshot-dev-secret'

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

function handle(req: IncomingMessage, res: ServerResponse) {
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
  if (method !== 'GET') return (log(501), djangoError(res, 501, 'Snapshot replay is read-only.'))

  const body = load(pathname)
  if (body === undefined) return (log(404), djangoError(res, 404, 'Not found.'))
  const out = Array.isArray(body) && url.search ? filterRows(body, url.searchParams) : body
  log(200)
  send(res, 200, out)
}

createServer(handle).listen(PORT, () => {
  console.log(`Snapshot backend on http://localhost:${PORT}  (${DIR})`)
  console.log(`  BACKEND_INTERNAL_URL=http://localhost:${PORT} bun run dev`)
})

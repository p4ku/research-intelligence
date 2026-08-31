#!/usr/bin/env bun
/**
 * Capture a read-only snapshot of a live Django backend — every GET the BFF
 * makes — into `local-data/<name>/`, so `snapshot:serve` can replay it as a
 * stand-in backend with real data and no network.
 *
 * Files mirror the URL: `/api/papers/<id>/` → `api/papers/<id>/index.json`.
 * List endpoints are captured unfiltered; the replay server applies query
 * filters (`?workspace=`, `?paper=`, `?status=`) itself.
 *
 * Env: CONTRACT_BASE_URL, CONTRACT_USER, CONTRACT_PASSWORD (same as
 * contract:check); SNAPSHOT_NAME (default `<host>-<YYYY-MM-DD>`).
 *
 * The snapshot is production data. `local-data/` is git- and docker-ignored;
 * keep it that way.
 */
import { mkdir, writeFile } from 'node:fs/promises'
import { join } from 'node:path'

const BASE = (process.env.CONTRACT_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')
const USER = process.env.CONTRACT_USER ?? 'admin'
const PASSWORD = process.env.CONTRACT_PASSWORD ?? 'schwarz123!'
const NAME =
  process.env.SNAPSHOT_NAME ??
  `${new URL(BASE).hostname.split('.')[0]}-${new Date().toISOString().slice(0, 10)}`
const OUT = join(import.meta.dir, '..', 'local-data', NAME)

/** Collections to capture, and which detail path to expand each item into. */
const COLLECTIONS: { list: string; detail?: (id: string) => string }[] = [
  { list: '/api/workspaces/', detail: (id) => `/api/workspaces/${id}/` },
  { list: '/api/papers/', detail: (id) => `/api/papers/${id}/` },
  { list: '/api/extractions/' },
  { list: '/api/pipeline-runs/' },
  { list: '/api/chat/sessions/', detail: (id) => `/api/chat/sessions/${id}/` },
]
const SINGLETONS = ['/api/auth/me/']

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

async function capture(path: string, token: string): Promise<unknown> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { authorization: `Bearer ${token}`, accept: 'application/json' },
  })
  if (!res.ok) {
    console.warn(`  skip ${path} (HTTP ${res.status})`)
    return undefined
  }
  const body: unknown = await res.json()
  const dir = join(OUT, path.replace(/^\/|\/$/g, ''))
  await mkdir(dir, { recursive: true })
  await writeFile(join(dir, 'index.json'), JSON.stringify(body, null, 2))
  return body
}

/** Run `fn` over `items` with at most `limit` in flight. */
async function eachLimit<T>(items: T[], limit: number, fn: (item: T) => Promise<void>) {
  let next = 0
  await Promise.all(
    Array.from({ length: Math.min(limit, items.length) }, async () => {
      while (next < items.length) await fn(items[next++])
    }),
  )
}

const token = await login()
const captured: string[] = []
console.log(`Snapshotting ${BASE} as ${USER} → ${OUT}`)

for (const path of SINGLETONS) {
  if ((await capture(path, token)) !== undefined) captured.push(path)
}
for (const { list, detail } of COLLECTIONS) {
  const body = await capture(list, token)
  if (body === undefined) continue
  captured.push(list)
  const rows = Array.isArray(body) ? (body as { id?: string }[]) : []
  console.log(`  ${list} ${rows.length} rows`)
  if (!detail) continue
  const ids = rows.map((r) => r.id).filter((id): id is string => typeof id === 'string')
  await eachLimit(ids, 4, async (id) => {
    if ((await capture(detail(id), token)) !== undefined) captured.push(detail(id))
  })
}

await writeFile(
  join(OUT, 'manifest.json'),
  JSON.stringify(
    { base: BASE, user: USER, capturedAt: new Date().toISOString(), paths: captured.sort() },
    null,
    2,
  ),
)
console.log(`Done: ${captured.length} responses in ${OUT}`)

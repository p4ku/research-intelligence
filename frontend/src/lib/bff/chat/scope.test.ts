/**
 * Guards the one rule a chat-history surface can silently break. Django lists
 * every session in a workspace to that workspace's admins and managers, so a
 * caller that lists sessions and then opens or deletes what it listed must ask
 * for `mine=1` — /ask shipped without it once already. Nothing in the type
 * system can catch that: the query parameter is optional by design (the BFF
 * contract keeps the unfiltered list for an overview that deliberately wants
 * the whole workspace), so this scans the source for list fetches instead.
 *
 * Detail fetches (`/bff/chat/sessions/${id}`) are out of scope: they carry no
 * query string and are authorised by Django per row.
 */
import { describe, expect, test } from 'bun:test'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const SRC = join(import.meta.dir, '..', '..', '..')

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else if (/\.(ts|tsx)$/.test(name) && !/\.test\.(ts|tsx)$/.test(name)) out.push(p)
  }
  return out
}

/** Every string literal in `src` that fetches the session LIST, with its file. */
function listFetches(): { file: string; url: string }[] {
  const found: { file: string; url: string }[] = []
  for (const file of walk(SRC)) {
    const text = readFileSync(file, 'utf8')
    for (const match of text.matchAll(/['"`](\/bff\/chat\/sessions\?[^'"`]*)['"`]/g)) {
      found.push({ file: relative(SRC, file), url: match[1]! })
    }
  }
  return found
}

describe('chat session list callers', () => {
  test('every list fetch scopes to the caller with mine=1', () => {
    const unscoped = listFetches().filter(({ url }) => !url.includes('mine=1'))
    expect(unscoped).toEqual([])
  })

  // Without this, deleting the last caller (or renaming the route) would make
  // the test above pass by finding nothing at all.
  test('the scan still finds the known callers', () => {
    const files = new Set(listFetches().map(({ file }) => file))
    expect(files).toContain('app/(sidebar)/ask/ask.tsx')
    expect(files).toContain('app/(sidebar)/papers/[id]/use-paper-thread.ts')
  })
})

#!/usr/bin/env bun
/**
 * Scope check: this team's provenance is `frontend/`. The repo also carries
 * the Django backend and shared docs, worked on by other people, so a branch
 * from here that quietly edits `backend/` or a root file is a merge conflict
 * waiting to happen — and a review nobody asked for.
 *
 * Compares the working tree against the merge base with the trunk and fails
 * if anything outside `frontend/` changed. Wired into `bun run check`.
 *
 *   bun run scope:check
 *   bun run scope:check --base origin/develop   # compare against another trunk
 *
 * A change outside `frontend/` is not forbidden, it is just never incidental:
 * make it its own branch, or say so in the PR.
 */
const SCOPE = 'frontend/'

// Every path is reported relative to the repo root, so the check reads the
// same whether it is run from `frontend/` or from the checkout above it.
const root = (() => {
  const { stdout, exitCode } = Bun.spawnSync(['git', 'rev-parse', '--show-toplevel'])
  return exitCode === 0 ? new TextDecoder().decode(stdout).trim() : process.cwd()
})()

function git(...args: string[]): string {
  const { stdout, exitCode } = Bun.spawnSync(['git', '-C', root, ...args])
  return exitCode === 0 ? new TextDecoder().decode(stdout).trim() : ''
}

const baseFlag = process.argv.indexOf('--base')
const requested = baseFlag === -1 ? null : process.argv[baseFlag + 1]
const base =
  requested ??
  ['origin/main', 'main'].find((ref) => git('rev-parse', '--verify', '--quiet', ref) !== '')

if (!base) {
  console.log('· no trunk to compare against — skipping scope check')
  process.exit(0)
}

// Merge base, so a stale branch is not blamed for the trunk's own commits.
const mergeBase = git('merge-base', base, 'HEAD') || base
const committed = git('diff', '--name-only', mergeBase, 'HEAD')
// `--` keeps the working tree (staged and unstaged) in the same comparison.
const working = git('diff', '--name-only', 'HEAD')
const untracked = git('ls-files', '--others', '--exclude-standard')

const changed = [...new Set([committed, working, untracked].join('\n').split('\n'))].filter(Boolean)
const outside = changed.filter((file) => !file.startsWith(SCOPE)).sort()

if (outside.length === 0) {
  console.log(`✓ ${changed.length} changed file(s), all inside ${SCOPE}`)
  process.exit(0)
}

console.error(`✗ ${outside.length} changed file(s) outside ${SCOPE}, compared against ${base}:`)
for (const file of outside) console.error(`    ${file}`)
console.error('\n  Move them to their own branch, or call them out deliberately in the PR.')
process.exit(1)

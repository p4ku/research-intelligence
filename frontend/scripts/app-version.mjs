// The frontend's version: `<major>.<minor>.<n>`.
//
// `major.minor` come from package.json (bump those by hand when the product
// moves); `n` is the number of commits on the current branch that touched this
// directory, so every frontend change that lands on main gets a new, strictly
// increasing number with no bump commits and no CI write-back. The same number
// falls out of a local `bun run build`, and `APP_VERSION` overrides everything
// for builds that have no git checkout (the Docker image — deploy.yml computes
// it on the runner and passes it as a build arg).
//
//   node scripts/app-version.mjs      # prints e.g. 0.1.45
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

/** @typedef {Record<string, string | undefined>} Env */

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')

/** @param {string[]} args */
function git(...args) {
  return execFileSync('git', args, { cwd: root, stdio: ['ignore', 'pipe', 'ignore'] })
    .toString()
    .trim()
}

/**
 * `0.1` from a package.json version of `0.1.0`.
 * @param {string} packageVersion
 */
export function versionPrefix(packageVersion) {
  const [major = '0', minor = '0'] = packageVersion.split('.')
  return `${major}.${minor}`
}

/**
 * `0.1.45` from a prefix and a commit count; `0.1.0-local` when the count is unknown.
 * @param {string} prefix
 * @param {number | null} commitCount
 */
export function composeVersion(prefix, commitCount) {
  return commitCount === null ? `${prefix}.0-local` : `${prefix}.${commitCount}`
}

/** @param {Env} [env] */
export function resolveAppVersion(env = process.env) {
  if (env.APP_VERSION) return env.APP_VERSION
  const pkg = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8'))
  const prefix = versionPrefix(pkg.version)
  try {
    return composeVersion(prefix, Number(git('rev-list', '--count', 'HEAD', '--', '.')))
  } catch {
    return composeVersion(prefix, null)
  }
}

/**
 * Full commit sha: `BUILD_ID` (what deploy.yml passes) or the local HEAD.
 * @param {Env} [env]
 */
export function resolveAppCommit(env = process.env) {
  if (env.BUILD_ID) return env.BUILD_ID
  try {
    return git('rev-parse', 'HEAD')
  } catch {
    return null
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  console.log(resolveAppVersion())
}

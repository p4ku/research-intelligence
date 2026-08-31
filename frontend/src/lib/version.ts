/**
 * Build-time facts, inlined by next.config.mjs (see scripts/app-version.mjs)
 * so they are the same on the server and in the browser and need no runtime
 * env. Safe to import anywhere.
 */

/** `0.1.45` — major.minor from package.json, patch = frontend commit count. */
export const appVersion = process.env.APP_VERSION ?? '0.0.0-local'

/** Full commit sha the build was made from, when known. */
export const appCommit = process.env.APP_COMMIT || null

/** ISO timestamp of the build. */
export const appBuiltAt = process.env.APP_BUILT_AT || null

/** `4645cef · 2026-08-31 14:02 UTC` — for tooltips and status pages. */
export function buildDetail(): string | null {
  const parts = [
    appCommit?.slice(0, 7),
    appBuiltAt && `${appBuiltAt.slice(0, 16).replace('T', ' ')} UTC`,
  ].filter(Boolean)
  return parts.length ? parts.join(' · ') : null
}

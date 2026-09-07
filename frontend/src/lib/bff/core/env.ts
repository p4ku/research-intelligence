/**
 * Integer knobs from the environment, read once with a literal default —
 * the same shape `sourceOf` gives the BFF sources: a bad value warns once
 * and falls back rather than failing the process. The defaults are also
 * written into `.env.example`, where they are documented. Pure apart from
 * `process.env`.
 */
const warned = new Set<string>()

export function intEnv(
  name: string,
  fallback: number,
  { min = Number.NEGATIVE_INFINITY, env = process.env as Record<string, string | undefined> } = {},
): number {
  const raw = env[name]?.trim()
  if (!raw) return fallback
  const value = Number(raw)
  if (Number.isInteger(value) && value >= min) return value
  if (!warned.has(name)) {
    warned.add(name)
    console.warn(`[bff] ${name}=${raw} is not an integer >= ${min}; using ${fallback}`)
  }
  return fallback
}

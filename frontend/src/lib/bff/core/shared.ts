/**
 * One instance per process, whichever module asks first.
 *
 * Next compiles route handlers and pages as separate server layers, each
 * with its own copy of every module, so a plain module-level singleton
 * exists once per layer: state written by `/bff/papers` is invisible to
 * Home, held twice over, and cleared by the start route in one layer only.
 * Anything that must be shared across a whole process is registered here
 * under a name instead. Pure.
 */
const registry = globalThis as unknown as Record<symbol, unknown>

export function sharedInstance<T>(name: string, make: () => T): T {
  const key = Symbol.for(`sri.bff.${name}`)
  if (!(key in registry)) registry[key] = make()
  return registry[key] as T
}

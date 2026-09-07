/** An injectable clock for tests of time-aware modules (TtlCache, the snapshot store). */
export function clock(start = 1_000) {
  let t = start
  return { now: () => t, tick: (ms: number) => (t += ms) }
}

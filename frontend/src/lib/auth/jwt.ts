// Unverified JWT payload decoding. The frontend only needs `exp` to decide
// when to refresh; Django verifies signatures on every API call.

export function decodeJwtPayload(token: string): Record<string, unknown> | null {
  const parts = token.split('.')
  if (parts.length !== 3) return null
  try {
    const parsed: unknown = JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8'))
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : null
  } catch {
    return null
  }
}

/** Seconds until the token's `exp`; 0 when absent or unparseable. */
export function secondsUntilExpiry(token: string, now: number = Date.now()): number {
  const exp = decodeJwtPayload(token)?.exp
  if (typeof exp !== 'number') return 0
  return exp - Math.floor(now / 1000)
}

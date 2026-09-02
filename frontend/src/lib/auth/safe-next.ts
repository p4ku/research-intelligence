/** A post-login target must be a local path — never a scheme, host, or /auth loop. */
export function safeNext(next: string | undefined | null): string {
  if (
    typeof next === 'string' &&
    next.startsWith('/') &&
    !next.startsWith('//') &&
    // The WHATWG URL parser strips tab/CR/LF anywhere and treats \ as /, so
    // '/\t/evil.com' or '/\evil.com' would resolve off-origin at the sink.
    !/[\t\n\r\\]/.test(next) &&
    !next.startsWith('/auth')
  ) {
    return next
  }
  return '/dashboard'
}

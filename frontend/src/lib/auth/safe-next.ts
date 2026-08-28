/** A post-login target must be a local path — never a scheme, host, or /auth loop. */
export function safeNext(next: string | undefined | null): string {
  if (
    typeof next === 'string' &&
    next.startsWith('/') &&
    !next.startsWith('//') &&
    !next.startsWith('/\\') &&
    !next.startsWith('/auth')
  ) {
    return next
  }
  return '/dashboard'
}

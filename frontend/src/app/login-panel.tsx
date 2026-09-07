'use client'

import { ScannerMark } from '@/components/brand'
import { ErrorNote } from '@/components/scanner-ui'
import { fmt, makeT, type Lang } from '@/lib/i18n'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { LoginErrorCode } from './auth/login/route'

// English fallbacks per /auth/login error code; t() renders them in the
// interface language. Kept as full sentences so the dictionary keys read.
const ERROR_TEXT: Record<LoginErrorCode, string> = {
  'cross-site': 'The sign-in request was rejected. Reload the page and try again.',
  'invalid-request': 'The sign-in request was rejected. Reload the page and try again.',
  'missing-credentials': 'Enter your email or username and password.',
  unreachable: 'The service cannot be reached right now. Please try again shortly.',
  credentials: 'Those credentials did not match. Please try again.',
  upstream: 'The sign-in could not be processed (HTTP {status}).',
}

// The only two codes that are a verdict on what was typed. Everything else is
// the platform failing, so the fields must not be marked invalid for it.
const FIELD_ERRORS = new Set<LoginErrorCode>(['credentials', 'missing-credentials'])

/** Both fields describe themselves by the error region while one is showing. */
const ERROR_ID = 'login-error'

export function LoginPanel({ next, notice, lang }: { next?: string; notice?: string; lang: Lang }) {
  // The login page renders outside the app shell (no LanguageProvider), so
  // the server page resolves the language and hands it in as a prop.
  const t = useMemo(() => makeT(lang), [lang])
  // The code travels with the sentence: the fields are marked invalid for a
  // rejected credential, but not for an outage, which is nothing they typed.
  const [error, setError] = useState<{ code: LoginErrorCode; text: string } | null>(null)
  const [loading, setLoading] = useState(false)
  const errorRef = useRef<HTMLDivElement>(null)

  // Move focus to the message on failure, rather than leaving keyboard and
  // screen-reader users to hunt for what changed.
  useEffect(() => {
    if (error) errorRef.current?.focus()
  }, [error])

  async function signIn(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setError(null)
    setLoading(true)
    const identifier = form.get('identifier') as string
    const password = form.get('password') as string
    // The route handler exchanges these for Django's JWT pair and sets the
    // session cookies; Django accepts either a username or an email here.
    let data: { redirect?: string; code?: LoginErrorCode; status?: number } = {}
    try {
      const res = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ identifier, password, next }),
      })
      data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error('login-failed')
    } catch {
      // The route handler always answers with a code (see auth/login/route.ts),
      // so arriving here without one means the response never came back or
      // wasn't JSON — the platform failing, not a password being rejected.
      // Defaulting to 'credentials' told people mid-outage to retype a
      // password that was correct all along.
      const code = data.code ?? 'unreachable'
      const text = ERROR_TEXT[code] ?? ERROR_TEXT.unreachable
      setError({ code, text: fmt(t(text), { status: data.status ?? '' }) })
      setLoading(false)
      return
    }
    // Full navigation so the server tree renders with the new session.
    window.location.assign(data.redirect ?? '/dashboard')
  }

  return (
    <div className="w-full max-w-sm">
      <div className="flex items-center gap-2.5">
        <ScannerMark className="text-foreground size-9" />
        <span className="text-foreground text-base font-semibold tracking-[0.14em] uppercase">
          Research Intelligence
        </span>
      </div>

      <h1 className="mt-10 text-2xl font-semibold tracking-tight text-zinc-950 dark:text-white">
        {t('Sign in')}
      </h1>
      <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
        {t('Use your email or username and password to continue.')}
      </p>

      {notice && (
        <p className="mt-6 rounded-sm bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-500/10 dark:text-amber-200">
          {notice}
        </p>
      )}

      <form onSubmit={signIn} className="mt-8 space-y-4">
        <div>
          <label
            htmlFor="login-identifier"
            className="block text-sm font-medium text-zinc-800 dark:text-zinc-200"
          >
            {t('Email or username')}
          </label>
          <input
            id="login-identifier"
            type="text"
            name="identifier"
            autoComplete="username"
            required
            aria-describedby={error ? ERROR_ID : undefined}
            aria-invalid={error && FIELD_ERRORS.has(error.code) ? true : undefined}
            className="border-line bg-surface text-foreground focus:border-accent focus:ring-accent/25 dark:focus:ring-accent/25 mt-1.5 block w-full rounded-sm border px-3 py-2 text-sm shadow-sm placeholder:text-zinc-400 focus:ring-2 focus:outline-none"
          />
        </div>
        <div>
          <label
            htmlFor="login-password"
            className="block text-sm font-medium text-zinc-800 dark:text-zinc-200"
          >
            {t('Password')}
          </label>
          <input
            id="login-password"
            type="password"
            name="password"
            autoComplete="current-password"
            required
            aria-describedby={error ? ERROR_ID : undefined}
            aria-invalid={error && FIELD_ERRORS.has(error.code) ? true : undefined}
            className="border-line bg-surface text-foreground focus:border-accent focus:ring-accent/25 dark:focus:ring-accent/25 mt-1.5 block w-full rounded-sm border px-3 py-2 text-sm shadow-sm placeholder:text-zinc-400 focus:ring-2 focus:outline-none"
          />
        </div>
        {/* Inside the form and above the button: the fields point at it with
            aria-describedby, so it is read as part of what failed. ErrorNote
            carries the one role="alert". */}
        {error && (
          <div id={ERROR_ID} ref={errorRef} tabIndex={-1} className="outline-none">
            <ErrorNote>{error.text}</ErrorNote>
          </div>
        )}
        <button
          type="submit"
          disabled={loading}
          className="flex w-full items-center justify-center rounded-lg bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:opacity-60 dark:bg-white dark:text-zinc-950 dark:hover:bg-zinc-200"
        >
          {loading ? t('Signing in…') : t('Sign in')}
        </button>
      </form>

      <p className="mt-10 text-xs text-zinc-400 dark:text-zinc-500">
        {t(
          'Research Intelligence is an internal tool. Access is restricted to authorized accounts.',
        )}
      </p>
    </div>
  )
}

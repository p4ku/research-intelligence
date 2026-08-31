'use client'

import { ScannerMark } from '@/components/brand'
import { useState } from 'react'

export function LoginPanel({ next, notice }: { next?: string; notice?: string }) {
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function signIn(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setError(null)
    setLoading(true)
    const identifier = form.get('identifier') as string
    const password = form.get('password') as string
    // The route handler exchanges these for Django's JWT pair and sets the
    // session cookies; Django accepts either a username or an email here.
    let data: { redirect?: string; error?: string } = {}
    try {
      const res = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ identifier, password, next }),
      })
      data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.error)
    } catch (err) {
      setError(
        err instanceof Error && err.message
          ? err.message
          : 'Those credentials did not match. Please try again.',
      )
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
        Sign in
      </h1>
      <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
        Use your email or username and password to continue.
      </p>

      {notice && (
        <p className="mt-6 rounded-sm bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-500/10 dark:text-amber-200">
          {notice}
        </p>
      )}

      <form onSubmit={signIn} className="mt-8 space-y-4">
        <div>
          <label className="block text-sm font-medium text-zinc-800 dark:text-zinc-200">
            Email or username
          </label>
          <input
            type="text"
            name="identifier"
            autoComplete="username"
            required
            className="border-line bg-surface text-foreground focus:border-accent focus:ring-accent/25 dark:focus:ring-accent/25 mt-1.5 block w-full rounded-sm border px-3 py-2 text-sm shadow-sm placeholder:text-zinc-400 focus:ring-2 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-zinc-800 dark:text-zinc-200">
            Password
          </label>
          <input
            type="password"
            name="password"
            autoComplete="current-password"
            required
            className="border-line bg-surface text-foreground focus:border-accent focus:ring-accent/25 dark:focus:ring-accent/25 mt-1.5 block w-full rounded-sm border px-3 py-2 text-sm shadow-sm placeholder:text-zinc-400 focus:ring-2 focus:outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="flex w-full items-center justify-center rounded-lg bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:opacity-60 dark:bg-white dark:text-zinc-950 dark:hover:bg-zinc-200"
        >
          {loading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>

      {error && (
        <p className="mt-4 text-sm text-red-600 dark:text-red-400" role="alert">
          {error}
        </p>
      )}

      <p className="mt-10 text-xs text-zinc-400 dark:text-zinc-500">
        Research Intelligence is an internal tool. Access is restricted to authorized accounts.
      </p>
    </div>
  )
}

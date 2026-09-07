'use client'

import { Card, ErrorNote, SectionLabel } from '@/components/scanner-ui'
import { Spinner } from '@/components/ui/spinner'
import { bffFetch } from '@/lib/bff/client'
import { errorsFromSubmit } from '@/lib/bff/problem-copy'
import type { Preferences, Profile } from '@/lib/bff/settings/schema'
import type { T } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import { ExclamationTriangleIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import { useRouter } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'

/** One id per field name, shared by the label, the input and its error line. */
const fieldId = (name: string) => `settings-${name}`

/** How long a "saved" confirmation stays on screen. */
const DONE_MS = 5000

const inputClass =
  'border-line bg-surface text-foreground focus:border-accent focus:ring-accent/25 mt-1.5 block w-full rounded-sm border px-3 py-2 text-sm shadow-sm placeholder:text-zinc-400 focus:ring-2 focus:outline-none'

function Field({
  label,
  name,
  defaultValue,
  type = 'text',
  autoComplete,
  error,
}: {
  label: string
  name: string
  defaultValue?: string
  type?: string
  autoComplete?: string
  error?: string
}) {
  // Ids are derived from the field name so the label, the input and its error
  // can find each other without every caller having to invent one.
  const id = fieldId(name)
  const errorId = `${id}-error`
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-zinc-800 dark:text-zinc-200">
        {label}
      </label>
      <input
        id={id}
        type={type}
        name={name}
        defaultValue={defaultValue}
        autoComplete={autoComplete}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        className={inputClass}
      />
      {/* Described by the input rather than announced on its own: the
          form-level ErrorNote is the one role="alert" per submit. */}
      {error && (
        <p id={errorId} className="mt-1 flex items-start gap-1 text-xs text-negative">
          <ExclamationTriangleIcon aria-hidden="true" className="mt-px size-3.5 shrink-0" />
          {error}
        </p>
      )}
    </div>
  )
}

function SaveButton({ busy, children }: { busy: boolean; children: React.ReactNode }) {
  return (
    <button
      type="submit"
      disabled={busy}
      // Colour alone carried the pending state, which is invisible to anyone
      // not seeing it — the spinner and aria-busy say it in the other two ways.
      aria-busy={busy || undefined}
      className={clsx(
        'inline-flex items-center gap-2 rounded-sm px-3 py-1.5 text-sm font-medium transition-colors',
        busy
          ? 'bg-foreground/10 text-muted-foreground'
          : 'bg-foreground text-background hover:bg-foreground/85',
      )}
    >
      {busy && <Spinner className="size-3.5" aria-hidden="true" />}
      {children}
    </button>
  )
}

/**
 * Submit state with the never-silent invariant: a thrown error always yields
 * a non-empty `errors` map (errorsFromSubmit partitions field errors from
 * form-level ones), so a failed save can't grey the button and do nothing.
 */
function useSubmit(t: T, fieldNames: readonly string[], fallback: string) {
  const [busy, setBusy] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [done, setDone] = useState<string | null>(null)

  // Send focus to the first field the backend rejected, so the rejection is
  // where the cursor is rather than somewhere the user has to go looking.
  // `errors` only changes identity on a submit; `fieldNames` is an inline
  // literal at every call site, so it is held in a ref rather than a dep —
  // as a dep it would re-run this on every render and steal focus back.
  const namesRef = useRef(fieldNames)
  namesRef.current = fieldNames
  useEffect(() => {
    const first = namesRef.current.find((name) => errors[name])
    if (first) document.getElementById(fieldId(first))?.focus()
  }, [errors])

  // "Profile saved." used to sit there for the rest of the session, so it
  // stopped meaning "just now". Clear it once it has been read.
  useEffect(() => {
    if (!done) return
    const timer = setTimeout(() => setDone(null), DONE_MS)
    return () => clearTimeout(timer)
  }, [done])

  async function submit(work: () => Promise<string | null>) {
    setBusy(true)
    setErrors({})
    setDone(null)
    try {
      setDone(await work())
    } catch (error) {
      console.error('[settings]', error)
      setErrors(errorsFromSubmit(error, fieldNames, t, fallback))
    } finally {
      setBusy(false)
    }
  }
  return { busy, errors, done, submit }
}

/** Name, email, and username — saved to Django; the sidebar updates via the refreshed cookie. */
export function ProfileForm({ profile }: { profile: Profile }) {
  const t = useT()
  const router = useRouter()
  const { busy, errors, done, submit } = useSubmit(
    t,
    ['first_name', 'last_name', 'email', 'username'],
    t("Couldn't save your profile. Try again."),
  )

  return (
    <Card>
      <SectionLabel>{t('Profile')}</SectionLabel>
      <form
        className="mt-4 space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          const form = new FormData(e.currentTarget)
          void submit(async () => {
            await bffFetch('/bff/settings/profile', {
              method: 'PATCH',
              body: JSON.stringify({
                first_name: form.get('first_name'),
                last_name: form.get('last_name'),
                email: form.get('email'),
                username: form.get('username'),
              }),
            })
            router.refresh()
            return t('Profile saved.')
          })
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label={t('First name')}
            name="first_name"
            defaultValue={profile.first_name}
            autoComplete="given-name"
            error={errors.first_name}
          />
          <Field
            label={t('Last name')}
            name="last_name"
            defaultValue={profile.last_name}
            autoComplete="family-name"
            error={errors.last_name}
          />
        </div>
        <Field
          label={t('Email')}
          name="email"
          type="email"
          defaultValue={profile.email}
          autoComplete="email"
          error={errors.email}
        />
        <Field
          label={t('Username')}
          name="username"
          defaultValue={profile.username}
          autoComplete="username"
          error={errors.username}
        />
        {errors._ && <ErrorNote>{errors._}</ErrorNote>}
        <div className="flex items-center gap-3">
          <SaveButton busy={busy}>{t('Save profile')}</SaveButton>
          {done && (
            <span role="status" className="text-xs text-muted-foreground">
              {done}
            </span>
          )}
        </div>
      </form>
    </Card>
  )
}

/** Old / new / confirm — Django's validation messages surface per field. */
export function PasswordForm() {
  const t = useT()
  const { busy, errors, done, submit } = useSubmit(
    t,
    ['old_password', 'new_password', 'confirm_password'],
    t("Couldn't change your password. Try again."),
  )

  return (
    <Card>
      <SectionLabel>{t('Password')}</SectionLabel>
      <form
        className="mt-4 space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          const el = e.currentTarget
          const form = new FormData(el)
          void submit(async () => {
            await bffFetch('/bff/settings/password', {
              method: 'POST',
              body: JSON.stringify({
                old_password: form.get('old_password'),
                new_password: form.get('new_password'),
                confirm_password: form.get('confirm_password'),
              }),
            })
            el.reset()
            return t('Password changed.')
          })
        }}
      >
        <Field
          label={t('Current password')}
          name="old_password"
          type="password"
          autoComplete="current-password"
          error={errors.old_password}
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label={t('New password')}
            name="new_password"
            type="password"
            autoComplete="new-password"
            error={errors.new_password}
          />
          <Field
            label={t('Confirm new password')}
            name="confirm_password"
            type="password"
            autoComplete="new-password"
            error={errors.confirm_password}
          />
        </div>
        {errors._ && <ErrorNote>{errors._}</ErrorNote>}
        <div className="flex items-center gap-3">
          <SaveButton busy={busy}>{t('Change password')}</SaveButton>
          {done && (
            <span role="status" className="text-xs text-muted-foreground">
              {done}
            </span>
          )}
        </div>
      </form>
    </Card>
  )
}

/** The digest toggles, one per domain. Persisted through /bff/settings/preferences unless stubbed. */
export function NotificationSettings({
  domains,
  stubbed,
}: {
  domains: { id: string; name: string; initial: Preferences }[]
  stubbed: boolean
}) {
  const t = useT()
  return (
    <Card>
      <SectionLabel>{t('Notifications')}</SectionLabel>
      {stubbed && (
        <div className="mt-1 font-mono text-[11px] text-zinc-400 dark:text-zinc-500">
          {t('Currently saved for this session only.')}
        </div>
      )}
      <div className="mt-2 divide-y divide-zinc-950/5 dark:divide-white/5">
        {domains.map((d) => (
          <DigestToggle
            key={d.id}
            workspaceId={d.id}
            name={d.name}
            initial={d.initial}
            stubbed={stubbed}
          />
        ))}
      </div>
    </Card>
  )
}

function DigestToggle({
  workspaceId,
  name,
  initial,
  stubbed,
}: {
  workspaceId: string
  name: string
  initial: Preferences
  stubbed: boolean
}) {
  const t = useT()
  const [on, setOn] = useState(initial.digest_email)
  const [busy, setBusy] = useState(false)

  async function toggle() {
    const next = !on
    setOn(next)
    // Stubbed: the backend has nowhere to persist this yet, so it lives in this
    // browser session only — exactly what the note under the label promises.
    // Writing it server-side would share one setting across every user.
    if (stubbed) return
    setBusy(true)
    try {
      await bffFetch(`/bff/settings/preferences?workspace_id=${workspaceId}`, {
        method: 'PUT',
        body: JSON.stringify({ digest_email: next }),
      })
    } catch {
      setOn(!next) // roll back
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex items-start justify-between gap-4 py-3">
      <div>
        <div className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
          {t('Daily briefing email')} · {name}
        </div>
        <div className="text-xs text-zinc-400">{t('A morning digest of the top signals.')}</div>
      </div>
      <button
        onClick={() => void toggle()}
        disabled={busy}
        aria-label={`${t('Daily briefing email')} · ${name}`}
        className={clsx(
          'relative h-6 w-11 shrink-0 rounded-full transition',
          on ? 'bg-blue-600' : 'bg-zinc-300 dark:bg-zinc-700',
        )}
        role="switch"
        aria-checked={on}
      >
        <span
          className={clsx(
            'absolute top-0.5 size-5 rounded-full bg-white transition',
            on ? 'left-[22px]' : 'left-0.5',
          )}
        />
      </button>
    </div>
  )
}

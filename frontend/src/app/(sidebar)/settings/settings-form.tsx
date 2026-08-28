'use client'

import { Card, SectionLabel } from '@/components/scanner-ui'
import { bffFetch, BffClientError } from '@/lib/bff/client'
import type { Preferences, Profile } from '@/lib/bff/settings/schema'
import { useT } from '@/lib/i18n-client'
import clsx from 'clsx'
import { useRouter } from 'next/navigation'
import { useState } from 'react'

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
  return (
    <div>
      <label className="block text-sm font-medium text-zinc-800 dark:text-zinc-200">
        {label}
      </label>
      <input
        type={type}
        name={name}
        defaultValue={defaultValue}
        autoComplete={autoComplete}
        className={inputClass}
      />
      {error && <p className="text-warn mt-1 text-xs">{error}</p>}
    </div>
  )
}

function SaveButton({ busy, children }: { busy: boolean; children: React.ReactNode }) {
  return (
    <button
      type="submit"
      disabled={busy}
      className={clsx(
        'rounded-sm px-3 py-1.5 text-sm font-medium transition-colors',
        busy
          ? 'bg-foreground/10 text-muted-foreground'
          : 'bg-foreground text-background hover:bg-foreground/85',
      )}
    >
      {children}
    </button>
  )
}

function useSubmit() {
  const [busy, setBusy] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [done, setDone] = useState<string | null>(null)

  async function submit(work: () => Promise<string | null>) {
    setBusy(true)
    setErrors({})
    setDone(null)
    try {
      setDone(await work())
    } catch (error) {
      if (error instanceof BffClientError) {
        const fields: Record<string, string> = {}
        for (const [field, messages] of Object.entries(error.problem.errors ?? {})) {
          fields[field] = messages.join(' ')
        }
        if (Object.keys(fields).length === 0) fields._ = error.problem.detail ?? error.problem.title
        setErrors(fields)
      } else {
        setErrors({ _: String(error) })
      }
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
  const { busy, errors, done, submit } = useSubmit()

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
        {errors._ && <p className="text-warn text-sm">{errors._}</p>}
        <div className="flex items-center gap-3">
          <SaveButton busy={busy}>{t('Save profile')}</SaveButton>
          {done && <span className="text-muted-foreground text-xs">{done}</span>}
        </div>
      </form>
    </Card>
  )
}

/** Old / new / confirm — Django's validation messages surface per field. */
export function PasswordForm() {
  const t = useT()
  const { busy, errors, done, submit } = useSubmit()

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
        {errors._ && <p className="text-warn text-sm">{errors._}</p>}
        <div className="flex items-center gap-3">
          <SaveButton busy={busy}>{t('Change password')}</SaveButton>
          {done && <span className="text-muted-foreground text-xs">{done}</span>}
        </div>
      </form>
    </Card>
  )
}

/** The digest toggle, persisted through /bff/settings/preferences. */
export function NotificationSettings({
  workspaceId,
  initial,
  stubbed,
}: {
  workspaceId: string
  initial: Preferences
  stubbed: boolean
}) {
  const t = useT()
  const [on, setOn] = useState(initial.digest_email)
  const [busy, setBusy] = useState(false)

  async function toggle() {
    const next = !on
    setOn(next)
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
    <Card>
      <SectionLabel>{t('Notifications')}</SectionLabel>
      <div className="mt-2 divide-y divide-zinc-950/5 dark:divide-white/5">
        <div className="flex items-start justify-between gap-4 py-3">
          <div>
            <div className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
              {t('Daily briefing email')}
            </div>
            <div className="text-xs text-zinc-400">{t('A morning digest of the top signals.')}</div>
            {stubbed && (
              <div className="mt-1 font-mono text-[11px] text-zinc-400 dark:text-zinc-500">
                {t('Not yet persisted by the backend — saved for this session only.')}
              </div>
            )}
          </div>
          <button
            onClick={() => void toggle()}
            disabled={busy}
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
      </div>
    </Card>
  )
}

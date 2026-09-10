'use client'

import { Button } from '@/components/button'
import { Input } from '@/components/input'
import { Card, SectionLabel } from '@/components/scanner-ui'
import { Select } from '@/components/select'
import { Bone } from '@/components/skeleton'
import { bffFetch } from '@/lib/bff/client'
import { errorsFromSubmit } from '@/lib/bff/problem-copy'
import { fmt } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import { useRouter } from 'next/navigation'
import { useState, useTransition, type ReactNode } from 'react'
import { shiftDays } from './format'
import { isConflict } from './ledger'

/**
 * New briefing: a domain, a search window, one button — always on
 * Home, never a modal. One run at a time across all analysts: while any run
 * is processing the button is disabled and the note says which domain is
 * running. A start posts to the BFF and re-reads the page, so the new run
 * appears at the top of Recent Briefings as Processing.
 */

export interface RunDomain {
  id: string
  name: string
}

const FIELDS = ['workspace_id', 'start_date', 'end_date'] as const
/** The default window: a month back from today. */
const DEFAULT_WINDOW_DAYS = 30

function Field({
  label,
  error,
  children,
}: {
  label: ReactNode
  error?: string
  children: ReactNode
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-zinc-600 dark:text-zinc-300">
        {label}
      </span>
      {children}
      {error && <span className="mt-1 block text-xs text-negative">{error}</span>}
    </label>
  )
}

// Every layout class lives here so RunCardSkeleton cannot drift.
function RunCardFrame({
  title,
  domain,
  from,
  to,
  button,
  error,
  note,
  onSubmit,
  state,
}: {
  title: ReactNode
  domain: ReactNode
  from: ReactNode
  to: ReactNode
  button: ReactNode
  error?: ReactNode
  note: ReactNode
  onSubmit?: (e: React.FormEvent<HTMLFormElement>) => void
  state: 'loaded' | 'skeleton'
}) {
  return (
    <Card data-shape="home-run-card" data-state={state}>
      <SectionLabel>{title}</SectionLabel>
      <form className="mt-4 space-y-4" onSubmit={onSubmit}>
        <div data-row="domain">{domain}</div>
        <div className="grid grid-cols-2 gap-3">
          <div data-row="from">{from}</div>
          <div data-row="to">{to}</div>
        </div>
        <div data-row="button">{button}</div>
        {error}
        <p data-row="note" className="text-xs text-zinc-500 dark:text-zinc-400">
          {note}
        </p>
      </form>
    </Card>
  )
}

export function RunCard({
  domains,
  processing,
  today,
}: {
  domains: RunDomain[]
  /** The domain whose run is in flight, or null when none is. */
  processing: string | null
  /** YYYY-MM-DD from the server, so the default window is the same on both renders. */
  today: string
}) {
  const t = useT()
  const router = useRouter()
  const [pending, startTransition] = useTransition()
  const [domain, setDomain] = useState(domains[0]?.id ?? '')
  const [from, setFrom] = useState(() => shiftDays(today, -DEFAULT_WINDOW_DAYS))
  const [to, setTo] = useState(today)
  const [busy, setBusy] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})

  // The window ends today at the latest: the pickers freeze later days and a
  // typed one keeps the button off, since nothing is published in the future.
  const valid = domain !== '' && from !== '' && to !== '' && from <= to && to <= today
  const running = processing !== null
  const disabled = !valid || busy || pending || running

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (disabled) return
    setBusy(true)
    setErrors({})
    try {
      await bffFetch('/bff/pipeline-runs/start', {
        method: 'POST',
        body: JSON.stringify({ workspace_id: domain, start_date: from, end_date: to }),
      })
      // Django lists the run before it answers: re-read the page for the row.
      startTransition(() => router.refresh())
    } catch (error) {
      console.error('[home] start failed', error)
      setErrors(errorsFromSubmit(error, FIELDS, t, t("Couldn't start the run. Try again.")))
      // 409: another run is already in flight — re-read so the form locks.
      if (isConflict(error)) startTransition(() => router.refresh())
    } finally {
      setBusy(false)
    }
  }

  return (
    <RunCardFrame
      state="loaded"
      onSubmit={submit}
      title={t('New briefing')}
      domain={
        <Field label={t('Domain')} error={errors.workspace_id}>
          <Select name="workspace_id" value={domain} onChange={(e) => setDomain(e.target.value)}>
            {domains.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </Select>
        </Field>
      }
      from={
        <Field label={t('From')} error={errors.start_date}>
          <Input
            type="date"
            name="start_date"
            value={from}
            max={to && to < today ? to : today}
            onChange={(e) => setFrom(e.target.value)}
          />
        </Field>
      }
      to={
        <Field label={t('To')} error={errors.end_date}>
          <Input
            type="date"
            name="end_date"
            value={to}
            min={from || undefined}
            max={today}
            onChange={(e) => setTo(e.target.value)}
          />
        </Field>
      }
      button={
        <Button type="submit" className="w-full" disabled={disabled}>
          {busy || pending ? t('Starting…') : t('Start')}
        </Button>
      }
      error={
        errors._ && (
          <p role="alert" className="text-xs text-negative">
            {errors._}
          </p>
        )
      }
      note={
        running
          ? fmt(t('{domain} is running. Briefings and papers stay available meanwhile.'), {
              domain: processing,
            })
          : t('Briefings run one at a time. When this one finishes, it tops the list.')
      }
    />
  )
}

export function RunCardSkeleton() {
  const t = useT()
  const control = <Bone.Block className="h-11 w-full sm:h-9" />
  return (
    <RunCardFrame
      state="skeleton"
      title={t('New briefing')}
      domain={<Field label={t('Domain')}>{control}</Field>}
      from={<Field label={t('From')}>{control}</Field>}
      to={<Field label={t('To')}>{control}</Field>}
      button={<Bone.Block className="h-11 w-full sm:h-9" />}
      note={<Bone.Text lines={2} widths={['100%', '62%']} />}
    />
  )
}

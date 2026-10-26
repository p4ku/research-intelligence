'use client'

import { Button } from '@/components/button'
import { Input } from '@/components/input'
import { Card, SectionLabel } from '@/components/scanner-ui'
import { Select } from '@/components/select'
import { Bone } from '@/components/skeleton'
import { bffFetch } from '@/lib/bff/client'
import {
  admission,
  MAX_IN_FLIGHT_PER_DOMAIN,
  type Admission,
  type InFlightRun,
} from '@/lib/bff/pipeline-runs/admission'
import { errorsFromSubmit } from '@/lib/bff/problem-copy'
import { fmt, type T } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import clsx from 'clsx'
import { useRouter } from 'next/navigation'
import { useEffect, useState, useTransition, type ReactNode } from 'react'
import { shiftDays } from './format'
import { isConflict } from './ledger'

/**
 * New briefing: a domain, a search window, one button — always on
 * Home, never a modal. Runs go in parallel, up to five per domain and one
 * per search window (lib/bff/pipeline-runs/admission.ts, Django's rule):
 * the button is off only while the chosen domain is full or the chosen
 * window is already running, and the note says what is in flight. A start
 * posts to the BFF and re-reads the page, so the new run appears at the top
 * of Recent Briefings as Processing.
 */

/** "Hybrid Computing ×2, Retail Robotics" — the domains with runs in flight. */
function runningDomains(runs: readonly InFlightRun[]): string {
  const counts = new Map<string, number>()
  for (const run of runs) counts.set(run.workspace_name, (counts.get(run.workspace_name) ?? 0) + 1)
  return [...counts].map(([name, n]) => (n > 1 ? `${name} ×${n}` : name)).join(', ')
}

/** The form's note: why Start is off, else what is running. Exported for the test. */
export function runCardNote(verdict: Admission, inFlight: readonly InFlightRun[], t: T): string {
  const max = MAX_IN_FLIGHT_PER_DOMAIN
  if (!verdict.ok) {
    return verdict.reason === 'cap'
      ? fmt(t('{domain} has {max} briefings in progress. Wait for one to finish.'), {
          domain: verdict.domain,
          max,
        })
      : fmt(t('{domain} is already running this window.'), { domain: verdict.domain })
  }
  if (inFlight.length === 0) {
    return fmt(
      t(
        'Up to {max} briefings can run at once per domain. A new one tops the list when it finishes.',
      ),
      { max },
    )
  }
  return fmt(t('{n} running: {domains}'), {
    n: inFlight.length,
    domains: runningDomains(inFlight),
  })
}

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
  typeSelector,
  domain,
  from,
  to,
  slrPolicy,
  button,
  error,
  note,
  onSubmit,
  state,
}: {
  title: ReactNode
  typeSelector?: ReactNode
  domain: ReactNode
  from: ReactNode
  to: ReactNode
  slrPolicy?: ReactNode
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
        {typeSelector && <div data-row="type-selector">{typeSelector}</div>}
        <div data-row="domain">{domain}</div>
        <div className="grid grid-cols-2 gap-3">
          <div data-row="from">{from}</div>
          <div data-row="to">{to}</div>
        </div>
        {slrPolicy && <div data-row="slr-policy">{slrPolicy}</div>}
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
  inFlight,
  today,
}: {
  domains: RunDomain[]
  /** Every run in flight across the user's domains (not just the rows shown). */
  inFlight: InFlightRun[]
  /** YYYY-MM-DD from the server, so the default window is the same on both renders. */
  today: string
}) {
  const t = useT()
  const router = useRouter()
  const [pending, startTransition] = useTransition()
  const [briefingType, setBriefingType] = useState<'intelligence' | 'slr'>('intelligence')
  const [domain, setDomain] = useState(domains[0]?.id ?? '')
  const [from, setFrom] = useState(() => shiftDays(today, -DEFAULT_WINDOW_DAYS))
  const [to, setTo] = useState(today)
  const [busy, setBusy] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  // A start refused with 409: the page was stale. Kept apart from field
  // errors because the list, not the user, clears it (below).
  const [conflict, setConflict] = useState(false)

  // The window ends on the server's UTC today at the latest: the pickers grey
  // out later days, and a typed one marks the field and keeps Start off.
  const future = to !== '' && to > today
  const valid = domain !== '' && from !== '' && to !== '' && from <= to && !future
  // The same verdict the start route takes, so the note and the 409 agree.
  const verdict = admission(inFlight, {
    workspace_id: domain,
    start_date: from || undefined,
    end_date: to || undefined,
  })
  const disabled = !valid || busy || pending || !verdict.ok

  // Once the refresh a 409 asked for has landed and the note explains a
  // refusal, the alert would only repeat it. When the note does not — the
  // slot freed again meanwhile — the alert stays, so the click is accounted for.
  const flying = inFlight
    .map((run) => run.id)
    .sort()
    .join(',')
  useEffect(() => {
    if (!verdict.ok) setConflict(false)
  }, [flying, verdict.ok])

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (disabled) return
    setBusy(true)
    setErrors({})
    setConflict(false)
    try {
      await bffFetch('/bff/pipeline-runs/start', {
        method: 'POST',
        body: JSON.stringify({
          workspace_id: domain,
          start_date: from,
          end_date: to,
          run_type: briefingType,
        }),
      })
      // Django lists the run before it answers: re-read the page for the row.
      startTransition(() => router.refresh())
    } catch (error) {
      console.error('[home] start failed', error)
      // 409: the domain filled up, or this window started, since the page
      // rendered — say so and re-read, so the note explains the refusal.
      if (isConflict(error)) {
        setConflict(true)
        startTransition(() => router.refresh())
      } else {
        setErrors(errorsFromSubmit(error, FIELDS, t, t("Couldn't start the run. Try again.")))
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <RunCardFrame
      state="loaded"
      onSubmit={submit}
      title={t('New briefing')}
      typeSelector={
        <div>
          <span className="mb-1.5 block text-xs font-medium text-zinc-600 dark:text-zinc-300">
            {t('Briefing type')}
          </span>
          <div className="flex rounded-lg bg-zinc-100 p-1 dark:bg-zinc-800">
            <button
              type="button"
              onClick={() => setBriefingType('intelligence')}
              className={clsx(
                'flex-1 rounded-md py-1.5 text-xs font-semibold transition-colors',
                briefingType === 'intelligence'
                  ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
                  : 'text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200',
              )}
            >
              {t('Intelligence')}
            </button>
            <button
              type="button"
              onClick={() => setBriefingType('slr')}
              className={clsx(
                'flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5 text-xs font-semibold transition-colors',
                briefingType === 'slr'
                  ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
                  : 'text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200',
              )}
            >
              <span className="text-amber-500 dark:text-amber-400">★</span>
              {t('SLR Review')}
            </button>
          </div>
        </div>
      }
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
            invalid={future}
            onChange={(e) => setTo(e.target.value)}
          />
        </Field>
      }
      slrPolicy={
        briefingType === 'slr' ? (
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-zinc-700 dark:border-amber-400/20 dark:bg-amber-400/5 dark:text-zinc-300">
            <div className="font-semibold text-amber-800 dark:text-amber-300">
              {t('SLR Policy Active')}
            </div>
            <ul className="mt-1.5 space-y-1 text-zinc-600 dark:text-zinc-400">
              <li>• Checkpoint: Full-text screening gate</li>
              <li>• Quorum: 1 reviewer • Sample rate: 10%</li>
              <li>• Reviewer: Current user (Auto-assigned)</li>
            </ul>
          </div>
        ) : null
      }
      button={
        <Button type="submit" className="w-full" disabled={disabled}>
          {busy || pending
            ? t('Starting…')
            : briefingType === 'slr'
              ? t('Start SLR Briefing')
              : t('Start')}
        </Button>
      }
      error={
        (errors._ || conflict) && (
          <p role="alert" className="text-xs text-negative">
            {errors._ ??
              t('This domain changed since the page loaded. The list has been refreshed.')}
          </p>
        )
      }
      note={
        briefingType === 'slr'
          ? t('1 briefing will run with staged audit pause.')
          : runCardNote(verdict, inFlight, t)
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

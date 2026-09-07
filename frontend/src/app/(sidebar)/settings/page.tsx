import { Card, PageHeader, SectionLabel } from '@/components/scanner-ui'
import { WorkspaceNotice } from '@/components/workspace-notice'
import { forPage } from '@/lib/bff/core/page'
import { sourceOf } from '@/lib/bff/core/source'
import { settings } from '@/lib/bff/settings/service'
import { getT } from '@/lib/i18n-server'
import { getWorkspacesState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import Link from 'next/link'
import { NotificationSettings, PasswordForm, ProfileForm } from './settings-form'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT()
  return { title: t('Settings') }
}

export default async function SettingsPage() {
  const [t, state, profile] = await Promise.all([
    getT(),
    getWorkspacesState(),
    forPage(settings.profile()),
  ])
  const domains = state.kind === 'ok' ? state.all : []
  // Preferences are kept per domain; one fetch each, side by side.
  const preferences = await Promise.all(
    domains.map((ws) => forPage(settings.getPreferences(ws.id))),
  )
  const role = profile.is_superuser
    ? t('Administrator')
    : profile.is_staff
      ? t('Staff')
      : t('Analyst')

  return (
    <div className="max-w-3xl space-y-8">
      <PageHeader
        title={t('Settings')}
        description={t('Your profile, your domains, and how Research Intelligence reaches you.')}
      />

      <ProfileForm profile={profile} />

      <Card>
        <SectionLabel>{t('Account')}</SectionLabel>
        <dl className="mt-3 divide-y divide-zinc-950/5 text-sm dark:divide-white/5">
          <Row label={t('Signed in with')} value={t('Email & password')} />
          <Row label={t('Role')} value={role} />
        </dl>
      </Card>

      <PasswordForm />

      {domains.length > 0 && (
        <Card>
          <SectionLabel>{t('Domains')}</SectionLabel>
          <div className="mt-3 divide-y divide-zinc-950/5 dark:divide-white/5">
            {domains.map((ws) => {
              const activeScrapers = ws.scrapers.filter((s) => s.is_active)
              const activeDefinitions = ws.definitions.filter((d) => d.is_active)
              return (
                <div key={ws.id} className="py-3 first:pt-0 last:pb-0">
                  <div className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
                    {ws.name}
                  </div>
                  <dl className="mt-1 text-sm">
                    <Row
                      label={t('Sources')}
                      value={
                        activeScrapers.length > 0
                          ? activeScrapers.map((s) => s.provider).join(' · ')
                          : '—'
                      }
                      compact
                    />
                    <Row
                      label={t('Extraction definitions')}
                      value={
                        activeDefinitions.length > 0
                          ? activeDefinitions.map((d) => d.name).join(' · ')
                          : '—'
                      }
                      compact
                    />
                    <Row
                      label={t('Screening model')}
                      value={ws.screening_llm_model ?? '—'}
                      compact
                    />
                  </dl>
                </div>
              )
            })}
          </div>
          {/* Tuning left the sidebar with the domain switcher; the scoring
              dials stay reachable from here, one domain at a time. */}
          <p className="mt-4 text-sm">
            <Link
              href="/tuning"
              className="text-foreground font-medium underline-offset-2 hover:underline"
            >
              {t('See what each domain’s score weighs →')}
            </Link>
          </p>
        </Card>
      )}

      {state.kind === 'unavailable' && <WorkspaceNotice kind="unavailable" />}

      {domains.length > 0 && (
        <NotificationSettings
          domains={domains.map((ws, i) => ({ id: ws.id, name: ws.name, initial: preferences[i] }))}
          stubbed={sourceOf('preferences') === 'stub'}
        />
      )}
    </div>
  )
}

function Row({
  label,
  value,
  compact = false,
}: {
  label: string
  value: React.ReactNode
  compact?: boolean
}) {
  return (
    <div
      className={
        compact
          ? 'flex items-baseline justify-between gap-6 py-1'
          : 'flex items-center justify-between gap-6 py-2.5'
      }
    >
      <dt className="shrink-0 text-zinc-500 dark:text-zinc-400">{label}</dt>
      <dd className="text-right font-medium text-zinc-800 dark:text-zinc-100">{value}</dd>
    </div>
  )
}

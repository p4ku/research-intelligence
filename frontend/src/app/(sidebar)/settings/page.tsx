import { Card, PageHeader, SectionLabel } from '@/components/scanner-ui'
import { forPage } from '@/lib/bff/core/page'
import { sourceOf } from '@/lib/bff/core/source'
import { settings } from '@/lib/bff/settings/service'
import { describeCron } from '@/lib/cron'
import { getLang, getT } from '@/lib/i18n-server'
import { getCurrentWorkspace } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { NotificationSettings, PasswordForm, ProfileForm } from './settings-form'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT()
  return { title: t('Settings') }
}

export default async function SettingsPage() {
  const [t, lang, ws, profile] = await Promise.all([
    getT(),
    getLang(),
    getCurrentWorkspace(),
    forPage(settings.profile()),
  ])
  const preferences = ws ? await forPage(settings.getPreferences(ws.id)) : null
  const role = profile.is_superuser
    ? t('Administrator')
    : profile.is_staff
      ? t('Staff')
      : t('Analyst')

  const activeScrapers = ws?.scrapers.filter((s) => s.is_active) ?? []
  const activeDefinitions = ws?.definitions.filter((d) => d.is_active) ?? []

  return (
    <div className="max-w-3xl space-y-8">
      <PageHeader
        title={t('Settings')}
        description={t('Your profile, workspace, and how Research Intelligence reaches you.')}
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

      {ws && (
        <Card>
          <SectionLabel>{t('Workspace')}</SectionLabel>
          <dl className="mt-3 divide-y divide-zinc-950/5 text-sm dark:divide-white/5">
            <Row label={t('Name')} value={ws.name} />
            <Row
              label={t('Sources')}
              value={
                activeScrapers.length > 0 ? activeScrapers.map((s) => s.provider).join(' · ') : '—'
              }
            />
            <Row
              label={t('Extraction definitions')}
              value={
                activeDefinitions.length > 0
                  ? activeDefinitions.map((d) => d.name).join(' · ')
                  : '—'
              }
            />
            <Row label={t('Screening model')} value={ws.screening_llm_model ?? '—'} />
            <Row
              label={t('Digest schedule')}
              value={
                ws.digest_schedule
                  ? (describeCron(ws.digest_schedule, lang) ?? (
                      <code className="font-mono text-xs">{ws.digest_schedule}</code>
                    ))
                  : '—'
              }
            />
          </dl>
        </Card>
      )}

      {ws && preferences && (
        <NotificationSettings
          workspaceId={ws.id}
          initial={preferences}
          stubbed={sourceOf('preferences') === 'stub'}
        />
      )}
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-6 py-2.5">
      <dt className="shrink-0 text-zinc-500 dark:text-zinc-400">{label}</dt>
      <dd className="text-right font-medium text-zinc-800 dark:text-zinc-100">{value}</dd>
    </div>
  )
}

import { Card, PageHeader, SectionLabel } from '@/components/scanner-ui'
import { WorkspaceNotice } from '@/components/workspace-notice'
import { forPage } from '@/lib/bff/core/page'
import { settings } from '@/lib/bff/settings/service'
import { APP_NAME } from '@/lib/config'
import { fmt } from '@/lib/i18n'
import { getT } from '@/lib/i18n-server'
import { getWorkspacesState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import { PasswordForm, ProfileForm } from './settings-form'

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
  const role = profile.is_superuser
    ? t('Administrator')
    : profile.is_staff
      ? t('Staff')
      : t('Analyst')

  return (
    <div className="max-w-3xl space-y-8">
      <PageHeader
        title={t('Settings')}
        description={fmt(
          t('Your profile and how you sign in to {appName}.'),
          { appName: APP_NAME },
        )}
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

      {state.kind === 'unavailable' && <WorkspaceNotice kind="unavailable" />}
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

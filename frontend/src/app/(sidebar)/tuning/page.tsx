import { Card, DomainBadge, PageHeader, SectionLabel } from '@/components/scanner-ui'
import { InfluenceBar, TuningPanel } from '@/components/tuning-panel'
import { WorkspaceNotice } from '@/components/workspace-notice'
import { forPage } from '@/lib/bff/core/page'
import { scoring } from '@/lib/bff/scoring/service'
import { getT } from '@/lib/i18n-server'
import { fallbackDimensions, tuningProfile } from '@/lib/papers/tuning-profile'
import { getWorkspacesState } from '@/lib/workspace-server'
import type { Metadata } from 'next'
import Link from 'next/link'
import { DomainTabs } from './domain-tabs'

export const dynamic = 'force-dynamic'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT()
  return { title: t('Tuning') }
}

// What steers the ranking, without the formula. The shares come from the
// verified mirror in lib/papers/tuning-profile.ts, never from the scoring
// BFF's `weights` — that array is an even placeholder split flagged
// weights_source: 'stub', and rendering it would invent this page's whole
// claim. No proof, no numbers: the fallback names the dimensions and stops.
//
// Scoring is per domain, so the page shows one domain at a time: `?domain=`
// picks it, the first membership is the default, and a tab strip switches
// when there are several.

export default async function TuningPage({
  searchParams,
}: {
  searchParams: Promise<{ domain?: string }>
}) {
  const [t, state, { domain }] = await Promise.all([getT(), getWorkspacesState(), searchParams])

  if (state.kind !== 'ok') {
    return (
      <div className="space-y-8">
        <PageHeader eyebrow={t('Controls')} title={t('Tuning')} />
        <WorkspaceNotice kind={state.kind} />
      </div>
    )
  }
  const ws = state.all.find((w) => w.id === domain) ?? state.all[0]
  const header = (
    <PageHeader
      eyebrow={t('Controls')}
      title={t('Tuning')}
      actions={state.all.length === 1 ? <DomainBadge name={ws.name} /> : undefined}
    />
  )
  const tabs = state.all.length > 1 && (
    <DomainTabs domains={state.all} current={ws.id} label={t('Choose a domain')} />
  )

  const s = await forPage(scoring.get(ws.id))
  const profile = tuningProfile(s)

  if (!profile) {
    const dimensions = fallbackDimensions(s)
    return (
      <div className="space-y-8">
        {header}
        {tabs}
        <Card>
          <SectionLabel>{t('What the score weighs')}</SectionLabel>
          {dimensions.length > 0 ? (
            <>
              <ul className="mt-4 space-y-2">
                {dimensions.map((name) => (
                  <li
                    key={name}
                    className="border-line-soft flex items-center gap-2 border-b pb-2 text-sm text-zinc-700 last:border-b-0 dark:text-zinc-200"
                  >
                    <span aria-hidden="true" className="bg-line-strong size-2 shrink-0" />
                    {name}
                  </li>
                ))}
              </ul>
              <p className="mt-4 text-xs text-zinc-500 dark:text-zinc-400">
                {t(
                  'How much each of these counts is not shown: the scoring method has changed, so the breakdown here could not be verified against a scored paper.',
                )}
              </p>
            </>
          ) : (
            <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
              {t('Nothing has been scored in this domain yet.')}
            </p>
          )}
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {header}
      {tabs}

      <Card>
        <SectionLabel>{t('What the score weighs')}</SectionLabel>
        <p className="mt-1.5 mb-5 text-sm text-zinc-500 dark:text-zinc-400">
          {t('Every paper in this domain is ranked on these, in this proportion.')}
        </p>
        <InfluenceBar profile={profile} />
      </Card>

      <Card>
        <TuningPanel profile={profile} />
      </Card>

      {s.example && (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {t('See it applied to a paper:')}{' '}
          <Link
            href={`/papers/${s.example.paper_id}`}
            className="text-foreground font-medium underline-offset-2 hover:underline"
          >
            {s.example.title}
          </Link>
        </p>
      )}
    </div>
  )
}

import { AnswerMarkdownSkeleton } from '@/components/answer-markdown'
import { FilterGroupSkeleton, MinScoreSliderSkeleton } from '@/components/filter-rail'
import { PaperCardSkeleton } from '@/components/paper-card'
import { Breadcrumbs, SectionLabel, StatBandSkeleton } from '@/components/scanner-ui'
import { Bone, Skeleton } from '@/components/skeleton'
import type { Features } from '@/lib/features'
import type { Lang, T } from '@/lib/i18n'
import Link from 'next/link'
import { editionHref, formatEditionDate } from '../format'
import { funnelCopy } from './sections'

/**
 * The edition page's section skeletons — the page's Suspense fallbacks and,
 * stacked, the loading.tsx shell. The page knows the date (and, from
 * `?domain=` and `?run=`, the domain and run) from the URL and passes them so
 * the crumb and the log link are real; loading.tsx does not get params, so
 * there they are bones.
 *
 * All three take the flags as a required prop — nothing outside this route
 * renders them — and must mirror the page: with `stars` off there is no star
 * toggle and no Starred chip, so neither gets a bone.
 */

export function EditionHeadSkeleton({
  t,
  lang,
  date,
  domain,
  features,
}: {
  t: T
  lang: Lang
  date?: string
  domain?: string
  features: Features
}) {
  const copy = funnelCopy(t)
  const dateLabel = date ? formatEditionDate(date, lang) : null
  return (
    <Skeleton.Region status={t('Loading the briefing')} innerClassName="space-y-10">
      <div className="space-y-4">
        <Breadcrumbs
          items={[
            { label: t('Briefings'), href: '/briefing' },
            {
              label: dateLabel ? (
                domain ? (
                  `${domain} · ${dateLabel}`
                ) : (
                  dateLabel
                )
              ) : (
                <Bone.Text widths={['20ch']} />
              ),
            },
          ]}
          t={t}
        />
        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
          <h1 className="min-w-0 flex-1 text-[26px]/8 font-semibold tracking-tight text-zinc-950 dark:text-white">
            <Bone.Text widths={['60%']} />
          </h1>
          {/* The briefing's star toggle. */}
          {features.stars && <Bone.Block className="mt-px h-[30px] w-28 shrink-0" />}
        </div>
      </div>

      <StatBandSkeleton
        count={3}
        labels={copy.map((c) => c.label)}
        subs={copy.map((c) => c.sub)}
        flow
        className="lg:grid-cols-3!"
      />

      <section>
        <SectionLabel size="sm">{t('In brief')}</SectionLabel>
        <AnswerMarkdownSkeleton
          className="mt-4 max-w-3xl text-base text-pretty text-zinc-600 dark:text-zinc-300"
          paragraphs={[3]}
        />
      </section>
    </Skeleton.Region>
  )
}

export function EditionPapersSkeleton({
  t,
  date,
  wsId,
  runId,
  cards = 5,
  sorts = 5,
  features,
}: {
  t: T
  date?: string
  /** The domain and run from the URL; without them the log link resolves the day's newest edition. */
  wsId?: string
  runId?: string
  cards?: number
  /** Sort options: the score, the date and one per scored dimension (three on prod). */
  sorts?: number
  features: Features
}) {
  return (
    <Skeleton.Region status={t('Loading the papers')}>
      <section>
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <SectionLabel size="sm">{t('The papers')}</SectionLabel>
          <span className="flex flex-wrap items-baseline justify-end gap-x-4 gap-y-1">
            <span className="font-mono text-[11px] whitespace-nowrap text-zinc-400 tabular-nums dark:text-zinc-500">
              <Bone.Text widths={['8ch']} />
            </span>
            {/* The Starred filter chip. */}
            {features.stars && <Bone.Chip width={82} />}
            {date ? (
              <Link
                href={editionHref(date, wsId, { runId, sub: 'run' })}
                className="text-xs font-medium whitespace-nowrap text-blue-600 hover:underline dark:text-blue-400"
              >
                {t('Screening log →')}
              </Link>
            ) : (
              <span className="text-xs font-medium">
                <Bone.Text widths={['12ch']} />
              </span>
            )}
          </span>
        </div>
        <div className="mt-5 grid gap-6 lg:grid-cols-3">
          <div className="space-y-3 lg:col-span-2">
            {Array.from({ length: cards }, (_, i) => (
              <PaperCardSkeleton key={i} />
            ))}
          </div>
          {/* The view's rail: the two labels are known, the options are not. */}
          <aside className="divide-y divide-line lg:col-span-1">
            <FilterGroupSkeleton label={t('Sort by')} rows={sorts} />
            <FilterGroupSkeleton label={t('Schwarz Score')}>
              <MinScoreSliderSkeleton
                labels={{
                  minimum: t('Minimum score'),
                  low: t('Any score'),
                  high: t('Only the strongest'),
                }}
              />
            </FilterGroupSkeleton>
          </aside>
        </div>
      </section>
    </Skeleton.Region>
  )
}

/** The loading.tsx shell. */
export function EditionPageSkeleton({
  t,
  lang,
  features,
}: {
  t: T
  lang: Lang
  features: Features
}) {
  return (
    <div className="space-y-10">
      <EditionHeadSkeleton t={t} lang={lang} features={features} />
      <EditionPapersSkeleton t={t} features={features} />
    </div>
  )
}

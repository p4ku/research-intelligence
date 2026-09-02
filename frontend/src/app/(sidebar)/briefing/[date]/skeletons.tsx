import { AnswerMarkdownSkeleton } from '@/components/answer-markdown'
import { PaperCardSkeleton } from '@/components/paper-card'
import { Breadcrumbs, SectionLabel, StatBandSkeleton } from '@/components/scanner-ui'
import { Bone, Skeleton } from '@/components/skeleton'
import type { Lang, T } from '@/lib/i18n'
import Link from 'next/link'
import { formatEditionDate } from '../format'
import { funnelCopy } from './sections'

/**
 * The edition page's section skeletons — the page's Suspense fallbacks and,
 * stacked, the loading.tsx shell. The page knows the date from the URL and
 * passes it so the crumb and the log link are real; loading.tsx does not get
 * params, so there they are bones.
 */

export function EditionHeadSkeleton({ t, lang, date }: { t: T; lang: Lang; date?: string }) {
  const copy = funnelCopy(t)
  return (
    <Skeleton.Region status={t('Loading the briefing')} innerClassName="space-y-10">
      <div className="space-y-4">
        <Breadcrumbs
          items={[
            { label: t('Briefings'), href: '/briefing' },
            { label: date ? formatEditionDate(date, lang) : <Bone.Text widths={['20ch']} /> },
          ]}
          t={t}
        />
        <h1 className="text-[26px]/8 font-semibold tracking-tight text-zinc-950 dark:text-white">
          <Bone.Text widths={['60%']} />
        </h1>
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
  cards = 5,
}: {
  t: T
  date?: string
  cards?: number
}) {
  return (
    <Skeleton.Region status={t('Loading the papers')}>
      <section>
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <SectionLabel size="sm">{t('The papers')}</SectionLabel>
          <span className="flex items-baseline gap-4">
            <span className="font-mono text-[11px] text-zinc-400 tabular-nums dark:text-zinc-500">
              <Bone.Text widths={['8ch']} />
            </span>
            {date ? (
              <Link
                href={`/briefing/${date}/run`}
                className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
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
        <div className="mt-5 space-y-3">
          {Array.from({ length: cards }, (_, i) => (
            <PaperCardSkeleton key={i} />
          ))}
        </div>
      </section>
    </Skeleton.Region>
  )
}

/** The loading.tsx shell. */
export function EditionPageSkeleton({ t, lang }: { t: T; lang: Lang }) {
  return (
    <div className="space-y-10">
      <EditionHeadSkeleton t={t} lang={lang} />
      <EditionPapersSkeleton t={t} />
    </div>
  )
}

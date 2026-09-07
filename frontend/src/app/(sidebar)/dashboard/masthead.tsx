import { AnswerMarkdown, AnswerMarkdownSkeleton } from '@/components/answer-markdown'
import { DomainBadge, SectionLabel } from '@/components/scanner-ui'
import { Bone } from '@/components/skeleton'
import { fmt, type T } from '@/lib/i18n'
import type { ReactNode } from 'react'
import { TextLink, TopPapers, TopPapersSkeleton, type HomePaper } from './home-ui'

/**
 * The masthead: the Current briefing read first, as a full-width band under
 * the search — its brief in serif, the funnel in one mono line, the three
 * strongest papers in a rail on the right. Server-rendered; `t` comes in.
 * The ledger below carries the same briefing as its highlighted row.
 */

export interface MastheadLead {
  domain: string
  /** The search window, already worded. */
  period: string
  /** The completion day, already worded. */
  generated: string
  /** The edition's permalink; null when no edition could be composed. */
  href: string | null
  /** Null when the run completed but no edition could be composed for it. */
  inBrief: string | null
  screened: number
  included: number
  top: HomePaper[]
}

const BRIEF_CLASS =
  'mt-4 max-w-2xl font-serif text-[16px]/6.5 text-pretty text-zinc-700 dark:text-zinc-200'

// Every layout class lives here so MastheadSkeleton cannot drift.
function MastheadFrame({
  meta,
  title,
  funnel,
  brief,
  link,
  railLabel,
  rail,
  state,
}: {
  meta: ReactNode
  title: ReactNode
  funnel: ReactNode
  brief: ReactNode
  link: ReactNode
  railLabel: ReactNode
  rail: ReactNode
  state: 'loaded' | 'skeleton'
}) {
  return (
    <section
      data-shape="home-masthead"
      data-state={state}
      className="grid gap-8 border-b border-line-soft pb-8 lg:grid-cols-3"
    >
      <div className="lg:col-span-2">
        <div data-row="meta" className="flex flex-wrap items-center gap-x-3 gap-y-1">
          {meta}
        </div>
        <h2
          data-row="title"
          className="mt-2.5 text-2xl font-semibold tracking-tight text-zinc-950 dark:text-white"
        >
          {title}
        </h2>
        <p
          data-row="funnel"
          className="mt-1.5 font-mono text-xs text-zinc-500 tabular-nums dark:text-zinc-400"
        >
          {funnel}
        </p>
        <div data-row="brief">{brief}</div>
        <div data-row="link" className="mt-3">
          {link}
        </div>
      </div>
      <div className="lg:col-span-1">
        <SectionLabel>{railLabel}</SectionLabel>
        {rail}
      </div>
    </section>
  )
}

export function Masthead({ lead, t }: { lead: MastheadLead; t: T }) {
  return (
    <MastheadFrame
      state="loaded"
      meta={
        <>
          <DomainBadge name={lead.domain} tone="quiet" />
          <span className="font-mono text-xs text-zinc-500 tabular-nums dark:text-zinc-400">
            {lead.period} · {fmt(t('generated {date}'), { date: lead.generated })}
          </span>
        </>
      }
      title={
        <>
          {lead.domain}
          <span className="font-normal text-zinc-500 dark:text-zinc-400"> — {lead.period}</span>
        </>
      }
      funnel={fmt(t('{screened} screened → {included} included → {lead} lead the briefing'), {
        screened: lead.screened,
        included: lead.included,
        lead: lead.top.length,
      })}
      brief={
        lead.inBrief !== null && <AnswerMarkdown text={lead.inBrief} className={BRIEF_CLASS} />
      }
      link={
        lead.href && (
          <TextLink href={lead.href} className="inline-block">
            {t('Open briefing →')}
          </TextLink>
        )
      }
      railLabel={t('Top of the briefing')}
      rail={
        lead.top.length > 0 ? (
          <TopPapers papers={lead.top} dense wrap className="mt-3" />
        ) : (
          <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
            {lead.inBrief === null
              ? t('The brief for this run is not available.')
              : t('No papers met the inclusion criteria for this briefing.')}
          </p>
        )
      }
    />
  )
}

export function MastheadSkeleton({ t }: { t: T }) {
  return (
    <MastheadFrame
      state="skeleton"
      meta={
        <>
          <Bone.Chip width={104} />
          <span className="font-mono text-xs">
            <Bone.Number digits={34} />
          </span>
        </>
      }
      title={<Bone.Text widths={['58%']} />}
      funnel={<Bone.Number digits={44} />}
      brief={<AnswerMarkdownSkeleton className={BRIEF_CLASS} paragraphs={[3]} />}
      link={
        <span className="text-xs font-medium">
          <Bone.Number digits={13} />
        </span>
      }
      railLabel={t('Top of the briefing')}
      rail={<TopPapersSkeleton dense wrap className="mt-3" />}
    />
  )
}

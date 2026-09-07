import { AnswerMarkdown } from '@/components/answer-markdown'
import { Card, DomainBadge, StatBand } from '@/components/scanner-ui'
import { forPage } from '@/lib/bff/core/page'
import { fmt, formatDate, type Lang, type T } from '@/lib/i18n'
import Link from 'next/link'
import { editionHref } from '../briefing/format'
import { editionToday, funnelCopy, latestRun, runPapers } from './data'
import { RunPapers } from './run-papers'

/**
 * The dashboard's streamed sections: one async Server Component per Suspense
 * boundary, each awaiting only its own data (through `forPage`, so a 401
 * still lands on /auth/logout). Every section returns a single root element —
 * the page wraps each in a <ViewTransition> pair with its skeleton.
 */

export async function TodayEyebrow({ t, lang }: { t: T; lang: Lang }) {
  const latest = await forPage(latestRun())
  const runDate = latest ? formatDate(latest.completed_at ?? latest.run_date, lang) : null
  return <>{runDate ? fmt(t('Today · {date}'), { date: runDate }) : t('Today')}</>
}

/** The domain the latest run belongs to — the header's badge, or nothing until a run exists. */
export async function TodayDomain() {
  const latest = await forPage(latestRun())
  return latest ? <DomainBadge name={latest.workspace_name} /> : null
}

export async function Funnel({ t }: { t: T }) {
  const { latest, papers } = await forPage(runPapers())
  const copy = funnelCopy(t)
  const funnel = [
    { value: latest?.total_papers_fetched ?? 0, ...copy[0] },
    { value: latest?.total_papers_passed_screening ?? 0, ...copy[1] },
    { value: papers.length, ...copy[2] },
  ]
  // Three stages, so override the band's default four columns.
  return <StatBand items={funnel} flow className="lg:grid-cols-3!" />
}

export async function BriefLink({ t, lang }: { t: T; lang: Lang }) {
  const edition = await forPage(editionToday(lang))
  if (!edition) return null
  return (
    <Link
      href={editionHref(edition.date, edition.workspace_id)}
      className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
    >
      {t('Open briefing →')}
    </Link>
  )
}

export async function Brief({ t, lang }: { t: T; lang: Lang }) {
  const edition = await forPage(editionToday(lang))
  if (!edition) {
    return (
      <p className="mt-4 max-w-3xl text-base leading-relaxed text-pretty text-zinc-600 dark:text-zinc-300">
        {t('No completed runs yet.')}
      </p>
    )
  }
  // The latest edition's brief (template-written until the backend's
  // reporting step produces prose — flagged when so).
  return (
    <div>
      <AnswerMarkdown
        text={edition.in_brief}
        className="mt-4 max-w-3xl text-base text-pretty text-zinc-600 dark:text-zinc-300"
      />
      {edition.in_brief_source === 'template' && (
        <p className="mt-2 font-mono text-[11px] text-zinc-400 dark:text-zinc-500">
          {t('Assembled automatically from this run.')}
        </p>
      )}
    </div>
  )
}

export async function Papers({ t }: { t: T }) {
  const { latest, workspace, papers } = await forPage(runPapers())
  if (!latest || !workspace) {
    return (
      <Card>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {t('Once a pipeline run completes, its papers appear here.')}
        </p>
      </Card>
    )
  }
  return <RunPapers papers={papers} workspace={workspace} />
}

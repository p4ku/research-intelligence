'use client'

import { PaperCard } from '@/components/paper-card'
import { SectionLabel } from '@/components/scanner-ui'
import { StarredChip } from '@/components/star'
import { fmt } from '@/lib/i18n'
import { useT } from '@/lib/i18n-client'
import type { ScoredPaper } from '@/lib/papers/types'
import { useStars } from '@/lib/stars-client'
import Link from 'next/link'
import { useState } from 'react'

/**
 * The edition's papers with the Starred filter. Client-side because the
 * filter reads the star store; the header row mirrors
 * EditionPapersSkeleton (skeletons.tsx) slot for slot.
 */
export function EditionPaperList({ papers, logHref }: { papers: ScoredPaper[]; logHref: string }) {
  const t = useT()
  const { isStarred } = useStars()
  const [starredOnly, setStarredOnly] = useState(false)

  const starred = papers.filter((p) => isStarred('paper', p.id))
  const shown = starredOnly ? starred : papers

  return (
    <section>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <SectionLabel size="sm">{t('The papers')}</SectionLabel>
        <span className="flex items-baseline gap-4">
          <span className="font-mono text-[11px] text-zinc-400 tabular-nums dark:text-zinc-500">
            {shown.length === 1 ? t('1 paper') : fmt(t('{n} papers'), { n: shown.length })}
          </span>
          <StarredChip
            active={starredOnly}
            count={starred.length}
            onToggle={() => setStarredOnly((v) => !v)}
          />
          <Link
            href={logHref}
            className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
          >
            {t('Screening log →')}
          </Link>
        </span>
      </div>
      <div className="mt-5 space-y-3">
        {shown.map((p) => (
          <PaperCard key={p.id} paper={p} />
        ))}
        {starredOnly && shown.length === 0 && (
          <div className="border-line rounded-sm border border-dashed p-10 text-center text-sm text-zinc-400">
            {t('Nothing starred yet.')}
          </div>
        )}
      </div>
    </section>
  )
}

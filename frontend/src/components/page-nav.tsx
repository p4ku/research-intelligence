'use client'

import { useT } from '@/lib/i18n-client'
import { ArrowLongLeftIcon, ArrowLongRightIcon } from '@heroicons/react/20/solid'
import clsx from 'clsx'

// A compact page range with ellipses: always the first and last page, plus a
// window around the current one. 'gap' marks a collapsed run of pages.
function pageItems(current: number, total: number): (number | 'gap')[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const items: (number | 'gap')[] = [1]
  const start = Math.max(2, current - 1)
  const end = Math.min(total - 1, current + 1)
  if (start > 2) items.push('gap')
  for (let p = start; p <= end; p++) items.push(p)
  if (end < total - 1) items.push('gap')
  items.push(total)
  return items
}

const edge =
  'inline-flex items-center border-t-2 border-transparent pt-4 text-sm font-medium text-zinc-500 transition-colors hover:border-zinc-300 hover:text-zinc-950 disabled:pointer-events-none disabled:opacity-40 dark:text-zinc-400 dark:hover:border-zinc-600 dark:hover:text-white'

const cell = 'inline-flex items-center border-t-2 px-4 pt-4 text-sm font-medium tabular-nums'

/**
 * Numbered pager with an accent top border marking the current page — the
 * counterpart to the section's top rule. Prev/Next carry long-arrow icons and
 * disable at the ends; the number strip collapses with ellipses past seven
 * pages and hides below md, where Prev/Next alone carry the load.
 */
export function PageNav({
  page,
  pageCount,
  onChange,
  labels,
  className,
}: {
  page: number
  pageCount: number
  onChange: (page: number) => void
  /** Translated Prev/Next labels; defaults are English. */
  labels?: { prev: string; next: string }
  className?: string
}) {
  const t = useT()
  if (pageCount <= 1) return null
  const prev = labels?.prev ?? 'Previous'
  const next = labels?.next ?? 'Next'

  return (
    <nav
      aria-label={t('Pagination')}
      className={clsx('flex items-center justify-between border-t border-line-soft', className)}
    >
      <div className="-mt-px flex w-0 flex-1">
        <button
          type="button"
          onClick={() => onChange(page - 1)}
          disabled={page <= 1}
          className={clsx(edge, 'pr-1')}
        >
          <ArrowLongLeftIcon
            aria-hidden="true"
            className="mr-3 size-5 text-zinc-400 dark:text-zinc-500"
          />
          {prev}
        </button>
      </div>

      <div className="-mt-px hidden md:flex">
        {pageItems(page, pageCount).map((it, i) =>
          it === 'gap' ? (
            <span
              key={`gap-${i}`}
              className={clsx(cell, 'border-transparent text-zinc-400 dark:text-zinc-500')}
            >
              …
            </span>
          ) : (
            <button
              key={it}
              type="button"
              onClick={() => onChange(it)}
              aria-current={it === page ? 'page' : undefined}
              className={clsx(
                cell,
                'transition-colors',
                it === page
                  ? 'border-accent text-zinc-950 dark:text-white'
                  : 'border-transparent text-zinc-500 hover:border-zinc-300 hover:text-zinc-950 dark:text-zinc-400 dark:hover:border-zinc-600 dark:hover:text-white',
              )}
            >
              {it}
            </button>
          ),
        )}
      </div>

      <div className="-mt-px flex w-0 flex-1 justify-end">
        <button
          type="button"
          onClick={() => onChange(page + 1)}
          disabled={page >= pageCount}
          className={clsx(edge, 'pl-1')}
        >
          {next}
          <ArrowLongRightIcon
            aria-hidden="true"
            className="ml-3 size-5 text-zinc-400 dark:text-zinc-500"
          />
        </button>
      </div>
    </nav>
  )
}

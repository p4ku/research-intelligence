import clsx from 'clsx'
import Link from 'next/link'

/**
 * One tab per domain, as links (`?domain=`), in the runs page's filter-strip
 * style. Tuning is per domain — the score formula and its dimensions belong
 * to a workspace — so the page shows one at a time.
 */
export function DomainTabs({
  domains,
  current,
  label,
}: {
  domains: { id: string; name: string }[]
  current: string
  label: string
}) {
  return (
    <nav className="flex flex-wrap items-center gap-1" aria-label={label}>
      {domains.map((d) => {
        const active = d.id === current
        return (
          <Link
            key={d.id}
            href={`/tuning?domain=${d.id}`}
            aria-current={active ? 'page' : undefined}
            className={clsx(
              'rounded-sm px-2.5 py-1 text-xs font-medium transition-colors',
              active
                ? 'bg-zinc-950 text-white dark:bg-white dark:text-zinc-950'
                : 'text-zinc-500 hover:bg-zinc-950/5 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-white/5 dark:hover:text-zinc-100',
            )}
          >
            {d.name}
          </Link>
        )
      })}
    </nav>
  )
}

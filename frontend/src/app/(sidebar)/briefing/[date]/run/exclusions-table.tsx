import { Bone } from '@/components/skeleton'
import type { Edition } from '@/lib/bff/briefings/schema'
import type { T } from '@/lib/i18n'
import type { ReactNode } from 'react'

/**
 * The screening log's table: what screened out and why. The frame owns the
 * columns; ExclusionsTable and ExclusionsTableSkeleton both fill it. Headers
 * carry data-row="col" so the drift check catches a bone that pushes a
 * column wider (widths are content-derived under whitespace-nowrap).
 */

function ExclusionsTableFrame({
  state,
  head,
  children,
}: {
  state: 'loaded' | 'skeleton'
  head: [ReactNode, ReactNode, ReactNode]
  children: ReactNode
}) {
  return (
    // Fixed columns: the paper column is the old max-w-xs, the source column a
    // nowrap word, the reason takes the rest — so the widths do not depend on
    // the content (a bone would otherwise get a different column than a title).
    <table data-shape="exclusions-table" data-state={state} className="mt-5 w-full table-fixed">
      <thead>
        <tr className="text-left text-xs text-zinc-500 dark:text-zinc-400">
          <th
            data-row="col"
            className="w-[45%] pr-6 pb-2 font-medium whitespace-nowrap sm:w-[20rem]"
          >
            {head[0]}
          </th>
          <th
            data-row="col"
            className="hidden w-24 pr-6 pb-2 font-medium whitespace-nowrap sm:table-cell"
          >
            {head[1]}
          </th>
          <th data-row="col" className="pb-2 font-medium whitespace-nowrap">
            {head[2]}
          </th>
        </tr>
      </thead>
      <tbody className="divide-y divide-zinc-950/5 dark:divide-white/5">{children}</tbody>
    </table>
  )
}

function ExclusionRow({
  title,
  source,
  reason,
}: {
  title: ReactNode
  source: ReactNode
  reason: ReactNode
}) {
  return (
    <tr data-row="exclusion" className="align-top">
      <td className="py-3 pr-6 text-sm font-medium text-zinc-800 dark:text-zinc-100">{title}</td>
      <td className="hidden py-3 pr-6 text-xs whitespace-nowrap text-zinc-400 sm:table-cell dark:text-zinc-500">
        {source}
      </td>
      <td className="py-3 text-sm leading-relaxed text-zinc-500 dark:text-zinc-400">{reason}</td>
    </tr>
  )
}

const head = (t: T): [string, string, string] => [t('Paper'), t('Source'), t('Why it did not pass')]

export function ExclusionsTable({ exclusions, t }: { exclusions: Edition['exclusions']; t: T }) {
  return (
    <ExclusionsTableFrame state="loaded" head={head(t)}>
      {exclusions.map((ex) => (
        <ExclusionRow
          key={ex.paper_id}
          title={ex.title}
          source={ex.source}
          reason={ex.reason ?? '—'}
        />
      ))}
    </ExclusionsTableFrame>
  )
}

/**
 * `shape` is the [title lines, reason lines] per row, cycled — titles wrap
 * inside max-w-xs about half the time; reasons run two to three lines.
 */
export function ExclusionsTableSkeleton({
  t,
  rows = 5,
  shape = [
    [2, 3],
    [1, 2],
  ],
}: {
  t: T
  rows?: number
  shape?: [number, number][]
}) {
  return (
    <ExclusionsTableFrame state="skeleton" head={head(t)}>
      {Array.from({ length: rows }, (_, i) => {
        const [title, reason] = shape[i % shape.length]
        return (
          <ExclusionRow
            key={i}
            title={<Bone.Text lines={title} widths={['100%', '58%']} />}
            source={<Bone.Text widths={['5ch']} />}
            reason={<Bone.Text lines={reason} widths={['100%', '92%', '40%']} />}
          />
        )
      })}
    </ExclusionsTableFrame>
  )
}

import { MagnifyingGlassIcon } from '@heroicons/react/16/solid'
import clsx from 'clsx'
import type { ComponentPropsWithoutRef, ReactNode } from 'react'

/**
 * The search field's chrome, shared by Home, Papers and Briefings so the
 * three fields read as one control. The leading slot is a fixed 20px box:
 * swapping the magnifier for a spinner never moves the text.
 */
export const SEARCH_FRAME =
  'group focus-within:border-accent/60 focus-within:ring-accent/15 border-line bg-surface relative flex items-center gap-3 rounded-md border px-4 py-3 transition focus-within:ring-4'

export function SearchFrame({
  leading,
  className,
  children,
  ...props
}: { leading?: ReactNode } & ComponentPropsWithoutRef<'div'>) {
  return (
    <div {...props} className={clsx(SEARCH_FRAME, className)}>
      <span className="grid size-5 shrink-0 place-items-center">
        {leading ?? (
          <MagnifyingGlassIcon className="size-5 text-zinc-400 transition-colors group-focus-within:text-accent" />
        )}
      </span>
      {children}
    </div>
  )
}

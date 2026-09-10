'use client'

import { useT } from '@/lib/i18n-client'
import clsx from 'clsx'
import { ChevronRightIcon } from 'lucide-react'
import { useId, useState } from 'react'

/**
 * The abstract, collapsed. It lives in the masthead's metadata card
 * (affiliation-flags.tsx) as its last row — "Abstract" with the disclosure
 * triangle the briefing rows use — under the compliance chips, and the
 * authors' text is hidden until that row is pressed, so the record's column
 * runs masthead, card, summary, assessment with nothing long in between.
 * A second press folds it away again.
 *
 * The panel stays mounted and opens on a grid-rows transition (0fr → 1fr;
 * none under reduced motion); closed it is `inert`, so its text is neither
 * focusable, findable nor read out. The button carries aria-expanded and
 * aria-controls, and nothing else in the row is interactive.
 */
export function AbstractDisclosure({ text }: { text: string }) {
  const t = useT()
  const id = useId()
  const [open, setOpen] = useState(false)

  return (
    <div data-row="abstract" className="-mx-1">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
        className={clsx(
          'group/abstract flex items-center gap-1 rounded-sm px-1 py-0.5 text-[11px] font-semibold tracking-[0.18em] text-zinc-700 uppercase transition-colors duration-150 ease-out hover:text-zinc-950 dark:text-zinc-300 dark:hover:text-white',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
        )}
      >
        {t('Abstract')}
        <ChevronRightIcon
          aria-hidden="true"
          strokeWidth={1.75}
          className={clsx(
            'size-3.5 text-zinc-400 transition-transform duration-200 ease-out group-hover/abstract:text-zinc-600 motion-reduce:transition-none dark:text-zinc-500 dark:group-hover/abstract:text-zinc-300',
            open && 'rotate-90',
          )}
        />
      </button>
      <div
        id={id}
        inert={!open}
        className={clsx(
          'grid transition-[grid-template-rows] duration-200 ease-out motion-reduce:transition-none',
          open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]',
        )}
      >
        <div className="min-h-0 overflow-hidden">
          <p className="max-w-[76ch] px-1 pt-1.5 pb-1 text-[13px] leading-relaxed text-pretty text-zinc-700 dark:text-zinc-300">
            {text}
          </p>
        </div>
      </div>
    </div>
  )
}

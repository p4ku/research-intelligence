'use client'

import { ArrowPathIcon } from '@heroicons/react/20/solid'
import { useLinkStatus } from 'next/link'
import type { ComponentType } from 'react'

/**
 * A sidebar item's leading icon that answers the click: while the link's
 * navigation is pending (the server is rendering the next page) it becomes a
 * turning arrow, then the icon returns. Rendered inside the item's <Link>,
 * which is what `useLinkStatus` reads; heroicons stamp `data-slot="icon"`,
 * so the item's own slot classes size and fill both, and nothing shifts.
 */
export function NavIcon({ Icon }: { Icon: ComponentType<{ className?: string }> }) {
  const { pending } = useLinkStatus()
  return pending ? <ArrowPathIcon className="animate-spin" aria-hidden="true" /> : <Icon />
}

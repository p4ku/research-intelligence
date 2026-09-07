'use client'

import type { ChatSession } from '@/lib/bff/chat/schema'
import { HistorySidecar } from '../../(sidebar)/ask/history-sidecar'
import { PaperPicker } from '../../(sidebar)/ask/paper-picker'
import type { PaletteEntry } from '../../(sidebar)/ask/types'

/**
 * Loaded panes for the ask surfaces. Both components take callbacks, which a
 * Server Component (the gallery page) cannot pass, so these client wrappers
 * supply inert ones.
 */

const noop = () => {}

export function HistorySidecarDemo({ threads }: { threads: ChatSession[] }) {
  return <HistorySidecar open threads={threads} activeId={null} onOpen={noop} onDelete={noop} />
}

export function PaperPickerDemo({ entries }: { entries: PaletteEntry[] }) {
  return (
    <PaperPicker
      entries={entries}
      query=""
      cursor={-1}
      placement="static"
      onCursor={noop}
      onPick={noop}
    />
  )
}

'use client'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useT } from '@/lib/i18n-client'
import {
  DocumentTextIcon,
  GlobeAltIcon,
  MagnifyingGlassIcon,
  PlayCircleIcon,
  PlusIcon,
  SparklesIcon,
} from '@heroicons/react/16/solid'
import type { ComponentType } from 'react'
import { ICON_BUTTON } from './console-frame'

/**
 * The composer's tool menu — the "+" that will grow every agentic capability
 * the assistant learns. Only attaching a paper is wired to anything today, so
 * the rest sit under a "Not yet available" label, disabled: naming them tells the
 * reader where this page is going without pretending it is already there.
 * Wire one up by moving it out of `soon` and giving it an `onSelect`.
 */
export function ToolMenu({ onAttach, disabled }: { onAttach: () => void; disabled?: boolean }) {
  const t = useT()

  const soon: {
    key: string
    Icon: ComponentType<{ className?: string }>
    label: string
    hint: string
  }[] = [
    {
      key: 'papers',
      Icon: MagnifyingGlassIcon,
      label: t('Across papers'),
      hint: t('Read the corpus and answer with citations'),
    },
    {
      key: 'web',
      Icon: GlobeAltIcon,
      label: t('Web search'),
      hint: t('Look beyond the scanned corpus'),
    },
    {
      key: 'run',
      Icon: PlayCircleIcon,
      label: t('Run a scan'),
      hint: t('Fetch new papers for a domain now'),
    },
    {
      key: 'deep',
      Icon: SparklesIcon,
      label: t('Deep research'),
      hint: t('Longer, multi-step investigation'),
    },
  ]

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        disabled={disabled}
        aria-label={t('Tools')}
        title={t('Tools')}
        className={ICON_BUTTON}
      >
        <PlusIcon className="size-4" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" sideOffset={8} className="w-72">
        <DropdownMenuItem onSelect={onAttach} className="items-start gap-2.5 py-2">
          <DocumentTextIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <span className="min-w-0">
            <span className="block font-medium text-foreground">{t('Attach a paper')}</span>
            <span className="block text-xs text-muted-foreground">
              {t("Scope to one paper's full text")}
            </span>
          </span>
        </DropdownMenuItem>

        <DropdownMenuLabel className="pt-2.5 pb-1 font-mono text-[10px] tracking-[0.18em] text-muted-foreground uppercase">
          {t('Not yet available')}
        </DropdownMenuLabel>
        {soon.map(({ key, Icon, label, hint }) => (
          <DropdownMenuItem key={key} disabled className="items-start gap-2.5 py-2">
            <Icon className="mt-0.5 size-4 shrink-0" />
            <span className="min-w-0">
              <span className="block font-medium">{label}</span>
              <span className="block text-xs">{hint}</span>
            </span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

'use client'

import {
  Dropdown,
  DropdownButton,
  DropdownItem,
  DropdownLabel,
  DropdownMenu,
} from '@/components/dropdown'
import { SidebarItem, SidebarLabel } from '@/components/sidebar'
import { useT } from '@/lib/i18n-client'
import { rememberWorkspace } from '@/lib/workspace'
import { CheckIcon, ChevronUpDownIcon } from '@heroicons/react/16/solid'
import { Squares2X2Icon } from '@heroicons/react/20/solid'
import { useRouter } from 'next/navigation'

export interface WorkspaceOption {
  id: string
  name: string
}

/**
 * Workspace is the backend's unit of scope (project, criteria, definitions),
 * so it sits at the top of the sidebar. Switching mirrors the language
 * toggle: write the cookie, refresh so server components re-read it.
 */
export function WorkspaceSwitcher({
  workspaces,
  currentId,
  mounted,
}: {
  workspaces: WorkspaceOption[]
  currentId: string | null
  mounted: boolean
}) {
  const t = useT()
  const router = useRouter()
  const current = workspaces.find((w) => w.id === currentId) ?? workspaces[0]

  if (workspaces.length === 0) {
    return (
      <SidebarItem>
        <Squares2X2Icon />
        <SidebarLabel className="text-zinc-400">{t('No workspace')}</SidebarLabel>
      </SidebarItem>
    )
  }

  // The dropdown mounts client-only (static lookalike during SSR) for the
  // same hydration reason as the account menu.
  if (!mounted || workspaces.length === 1) {
    return (
      <SidebarItem>
        <Squares2X2Icon />
        <SidebarLabel>{current.name}</SidebarLabel>
        {workspaces.length > 1 && <ChevronUpDownIcon />}
      </SidebarItem>
    )
  }

  function choose(id: string) {
    rememberWorkspace(id)
    router.refresh()
  }

  return (
    <Dropdown>
      <DropdownButton as={SidebarItem} aria-label={t('Switch workspace')}>
        <Squares2X2Icon />
        <SidebarLabel>{current.name}</SidebarLabel>
        <ChevronUpDownIcon />
      </DropdownButton>
      <DropdownMenu className="min-w-64" anchor="bottom start">
        {workspaces.map((w) => (
          <DropdownItem key={w.id} onClick={() => choose(w.id)}>
            {w.id === current.id ? <CheckIcon /> : <span className="size-4" aria-hidden="true" />}
            <DropdownLabel>{w.name}</DropdownLabel>
          </DropdownItem>
        ))}
      </DropdownMenu>
    </Dropdown>
  )
}

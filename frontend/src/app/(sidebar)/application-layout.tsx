'use client'

import { Navbar, NavbarItem, NavbarSection, NavbarSpacer } from '@/components/app-navbar'
import { Avatar } from '@/components/avatar'
import { ScannerMark } from '@/components/brand'
import {
  Dropdown,
  DropdownButton,
  DropdownDivider,
  DropdownItem,
  DropdownLabel,
  DropdownMenu,
} from '@/components/dropdown'
import {
  Sidebar,
  SidebarBody,
  SidebarFooter,
  SidebarHeader,
  SidebarItem,
  SidebarLabel,
  SidebarSection,
} from '@/components/sidebar'
import { SidebarLayout } from '@/components/sidebar-layout'
import { Switch } from '@/components/switch'
import { WorkspaceSwitcher, type WorkspaceOption } from '@/components/workspace-switcher'
import type { SessionUser } from '@/lib/auth/cookies'
import type { Lang } from '@/lib/i18n'
import { LanguageProvider, useLanguage, useT } from '@/lib/i18n-client'
import {
  ArrowRightStartOnRectangleIcon,
  ChevronUpIcon,
  LanguageIcon,
  ShieldCheckIcon,
  UserCircleIcon,
} from '@heroicons/react/16/solid'
import {
  ChatBubbleLeftRightIcon,
  Cog6ToothIcon,
  DocumentTextIcon,
  HomeIcon,
  NewspaperIcon,
  VariableIcon,
} from '@heroicons/react/20/solid'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'

const coreNav = [
  { href: '/dashboard', label: 'Today', Icon: HomeIcon, exact: true },
  { href: '/briefing', label: 'Briefings', Icon: NewspaperIcon },
  { href: '/papers', label: 'Papers', Icon: DocumentTextIcon },
  { href: '/scoring', label: 'Scoring', Icon: VariableIcon },
  { href: '/ask', label: 'Ask', Icon: ChatBubbleLeftRightIcon },
]

function AccountDropdownMenu({
  anchor,
  onSignOut,
}: {
  anchor: 'top start' | 'bottom end' | 'bottom start'
  onSignOut: () => void
}) {
  const { lang, toggle: toggleLanguage } = useLanguage()
  const t = useT()
  return (
    <DropdownMenu className="min-w-64" anchor={anchor}>
      <DropdownItem href="/settings">
        <UserCircleIcon />
        <DropdownLabel>{t('My account')}</DropdownLabel>
      </DropdownItem>
      <DropdownItem href="/settings">
        <Cog6ToothIcon />
        <DropdownLabel>{t('Settings')}</DropdownLabel>
      </DropdownItem>
      <DropdownDivider />
      <DropdownItem href="#">
        <ShieldCheckIcon />
        <DropdownLabel>{t('Privacy & access')}</DropdownLabel>
      </DropdownItem>
      <DropdownItem
        onClick={(e: React.MouseEvent) => {
          // preventDefault keeps the Headless UI menu open on toggle
          e.preventDefault()
          toggleLanguage()
        }}
      >
        <LanguageIcon />
        {/* Language self-name, so it stays findable from either language */}
        <DropdownLabel>Deutsch</DropdownLabel>
        <Switch
          as="span"
          checked={lang === 'de'}
          color="dark/zinc"
          className="pointer-events-none ml-auto"
        />
      </DropdownItem>
      <DropdownDivider />
      <DropdownItem onClick={onSignOut}>
        <ArrowRightStartOnRectangleIcon />
        <DropdownLabel>{t('Sign out')}</DropdownLabel>
      </DropdownItem>
    </DropdownMenu>
  )
}

function UserMenuLabel({ userName, userImage }: { userName: string; userImage?: string }) {
  return (
    <span className="flex min-w-0 items-center gap-3">
      <Avatar
        src={userImage ?? undefined}
        initials={userName[0]}
        className="size-6"
        square
        alt=""
      />
      <span className="truncate text-sm/5 font-medium text-zinc-950 dark:text-white">
        {userName}
      </span>
    </span>
  )
}

interface ShellProps {
  user: SessionUser
  workspaces: WorkspaceOption[]
  currentWorkspaceId: string | null
  children: React.ReactNode
}

export function ApplicationLayout({ lang, ...props }: ShellProps & { lang: Lang }) {
  return (
    <LanguageProvider lang={lang}>
      <ApplicationLayoutInner {...props} />
    </LanguageProvider>
  )
}

function ApplicationLayoutInner({ user, workspaces, currentWorkspaceId, children }: ShellProps) {
  const t = useT()
  const pathname = usePathname()
  // false until hydration completes; the user-menu Dropdown mounts client-only
  // so its generated ids are never compared against server HTML.
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true)
  }, [])

  const userName = user.name || 'Analyst'
  const userImage = user.image

  async function handleSignOut() {
    // Drops the session cookies; a full navigation clears the server tree.
    await fetch('/auth/logout', { method: 'POST' })
    window.location.assign('/')
  }

  return (
    <SidebarLayout
      navbar={
        <Navbar>
          <NavbarSpacer />
          <NavbarSection>
            {mounted ? (
              <Dropdown>
                <DropdownButton as={NavbarItem}>
                  <Avatar src={userImage ?? undefined} initials={userName[0]} square />
                </DropdownButton>
                <AccountDropdownMenu anchor="bottom end" onSignOut={handleSignOut} />
              </Dropdown>
            ) : (
              <NavbarItem>
                <Avatar src={userImage ?? undefined} initials={userName[0]} square />
              </NavbarItem>
            )}
          </NavbarSection>
        </Navbar>
      }
      sidebar={
        <Sidebar>
          {/* Fixed-height row with no vertical padding so the logo line sits
              on a stable h-14 header. */}
          <SidebarHeader>
            <div className="flex items-center gap-2.5 px-2 py-1.5">
              <ScannerMark className="text-foreground size-7" />
              <div className="min-w-0">
                <div className="text-foreground text-xs leading-snug font-semibold tracking-[0.14em] uppercase">
                  Research Intelligence
                </div>
              </div>
            </div>
          </SidebarHeader>

          <SidebarBody>
            <SidebarSection>
              <WorkspaceSwitcher
                workspaces={workspaces}
                currentId={currentWorkspaceId}
                mounted={mounted}
              />
            </SidebarSection>

            <SidebarSection>
              {coreNav.map(({ href, label, Icon, exact }) => (
                <SidebarItem
                  key={href}
                  href={href}
                  current={exact ? pathname === href : pathname.startsWith(href)}
                >
                  <Icon />
                  <SidebarLabel>{t(label, 'nav')}</SidebarLabel>
                </SidebarItem>
              ))}
            </SidebarSection>
          </SidebarBody>

          {/* User menu lives at the bottom of the sidebar; expanding it opens
              the account menu upward. The menu mounts client-only (with a
              static lookalike during SSR) so a session update landing
              mid-hydration can't desync its generated ids. */}
          <SidebarFooter className="max-lg:hidden">
            {mounted ? (
              <Dropdown>
                <DropdownButton as={SidebarItem}>
                  <UserMenuLabel userName={userName} userImage={userImage} />
                  <ChevronUpIcon />
                </DropdownButton>
                <AccountDropdownMenu anchor="top start" onSignOut={handleSignOut} />
              </Dropdown>
            ) : (
              <SidebarItem>
                <UserMenuLabel userName={userName} userImage={userImage} />
                <ChevronUpIcon />
              </SidebarItem>
            )}
          </SidebarFooter>
        </Sidebar>
      }
    >
      {children}
    </SidebarLayout>
  )
}

'use client'

import { Navbar, NavbarItem, NavbarSection, NavbarSpacer } from '@/components/app-navbar'
import { Avatar } from '@/components/avatar'
import { ScannerMark } from '@/components/brand'
import {
  Dropdown,
  DropdownButton,
  DropdownDivider,
  DropdownHeading,
  DropdownItem,
  DropdownLabel,
  DropdownMenu,
  DropdownSection,
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
import { Spinner } from '@/components/ui/spinner'
import { VersionStamp } from '@/components/version-stamp'
import type { SessionUser } from '@/lib/auth/cookies'
import { performSignOut } from '@/lib/auth/leave'
import { FEATURE_KEYS, FEATURES, isVisible, type FeatureKey, type Features } from '@/lib/features'
import { FeaturesProvider, useFeatures, useSetFeature } from '@/lib/features-client'
import type { Lang } from '@/lib/i18n'
import { LanguageProvider, useLanguage, useT } from '@/lib/i18n-client'
import {
  ArrowRightStartOnRectangleIcon,
  ChevronUpIcon,
  LanguageIcon,
} from '@heroicons/react/16/solid'
import {
  ChatBubbleLeftRightIcon,
  Cog6ToothIcon,
  DocumentTextIcon,
  HomeIcon,
  NewspaperIcon,
  PlayCircleIcon,
  Squares2X2Icon,
  StarIcon,
} from '@heroicons/react/20/solid'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'

interface ShellNavItem {
  href: string
  label: string
  Icon: React.ComponentType<{ className?: string }>
  /** Match the path exactly rather than by prefix (for index routes). */
  exact?: boolean
  /** Demo flag that hides this item when off (src/lib/features.ts). */
  feature?: FeatureKey
}

// The spec's header — Home | Briefings | Papers | Ask — plus Runs. Tuning is
// per domain and left the nav with the domain switcher; Settings links to it.
const coreNav: ShellNavItem[] = [
  { href: '/dashboard', label: 'Home', Icon: HomeIcon, exact: true },
  { href: '/briefing', label: 'Briefings', Icon: NewspaperIcon },
  { href: '/papers', label: 'Papers', Icon: DocumentTextIcon, feature: 'all_papers' },
  { href: '/ask', label: 'Ask', Icon: ChatBubbleLeftRightIcon },
  { href: '/runs', label: 'Runs', Icon: PlayCircleIcon },
]

const studioNav: ShellNavItem[] = [
  { href: '/studio/skeletons', label: 'Skeletons', Icon: Squares2X2Icon },
  { href: '/dashboard', label: 'Briefings app', Icon: HomeIcon, exact: true },
]

/**
 * Nav sets live here, in the client module, and callers pick one by name:
 * icon components are not serializable, so a server layout cannot hand them
 * across the boundary.
 */
const NAVS = { core: coreNav, studio: studioNav } as const

/** Which area of the product the shell is framing. */
export type ShellArea = keyof typeof NAVS

/** Badge shown beside the wordmark; the reading app is the unmarked default. */
const AREA_BADGE: Record<ShellArea, string | null> = { core: null, studio: 'Studio' }

/**
 * Icons for the demo-flag rows in the account menu. Kept here beside the nav
 * icons for the same serialisability reason; reuses the 20px set the nav
 * already imports (DropdownItem sizes icons itself).
 */
const FEATURE_ICONS: Record<FeatureKey, React.ComponentType<{ className?: string }>> = {
  all_papers: DocumentTextIcon,
  stars: StarIcon,
  ask: ChatBubbleLeftRightIcon,
}

function AccountDropdownMenu({
  anchor,
  signingOut,
  onSignOut,
}: {
  anchor: 'top start' | 'bottom end' | 'bottom start'
  signingOut: boolean
  onSignOut: () => void
}) {
  const { lang, toggle: toggleLanguage } = useLanguage()
  const features = useFeatures()
  const setFeature = useSetFeature()
  const t = useT()
  return (
    <DropdownMenu className="min-w-64" anchor={anchor}>
      <DropdownItem href="/settings">
        <Cog6ToothIcon />
        <DropdownLabel>{t('Settings')}</DropdownLabel>
      </DropdownItem>
      <DropdownDivider />
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
      {/* Demo flags: hide a feature live and put it back. These rows are never
          hidden themselves — they are how a feature comes back — and they show
          in the Studio menu too. */}
      <DropdownSection>
        <DropdownHeading>{t('Demo features')}</DropdownHeading>
        {FEATURE_KEYS.map((key) => {
          const Icon = FEATURE_ICONS[key]
          const def = FEATURES[key]
          return (
            <DropdownItem
              key={key}
              onClick={(e: React.MouseEvent) => {
                // Same trick as the language row: the menu stays open, so two
                // flags can be flipped without reopening it.
                e.preventDefault()
                setFeature(key, !features[key])
              }}
            >
              <Icon />
              <DropdownLabel>{t(def.label, def.ctx)}</DropdownLabel>
              <Switch
                as="span"
                checked={features[key]}
                color="dark/zinc"
                className="pointer-events-none ml-auto"
              />
            </DropdownItem>
          )
        })}
      </DropdownSection>
      <DropdownDivider />
      <DropdownItem
        disabled={signingOut}
        aria-busy={signingOut || undefined}
        onClick={(e: React.MouseEvent) => {
          // preventDefault keeps the menu open (the language-toggle trick
          // above), so the pending state stays visible until the sign-out
          // navigation commits.
          e.preventDefault()
          onSignOut()
        }}
      >
        {signingOut ? (
          <Spinner data-slot="icon" aria-hidden="true" />
        ) : (
          <ArrowRightStartOnRectangleIcon />
        )}
        <DropdownLabel>{signingOut ? t('Signing out…') : t('Sign out')}</DropdownLabel>
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
  children: React.ReactNode
  /** Which nav to show; defaults to the reading app's. */
  area?: ShellArea
}

export function ApplicationLayout({
  lang,
  features,
  ...props
}: ShellProps & { lang: Lang; features: Features }) {
  return (
    <LanguageProvider lang={lang}>
      <FeaturesProvider features={features}>
        <ApplicationLayoutInner {...props} />
      </FeaturesProvider>
    </LanguageProvider>
  )
}

function ApplicationLayoutInner({ user, children, area = 'core' }: ShellProps) {
  const features = useFeatures()
  // One render site feeds both the desktop rail and the mobile drawer
  // (sidebar-layout mounts the same node twice), so filtering here covers both.
  const nav = NAVS[area].filter((item) => isVisible(item, features))
  const areaBadge = AREA_BADGE[area]
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

  const [signingOut, setSigningOut] = useState(false)

  async function handleSignOut() {
    // performSignOut guarantees the outcome on every path (fallback GET
    // navigation when the POST fails) and guards re-entry; the state only
    // drives the menu's pending item.
    setSigningOut(true)
    await performSignOut()
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
                <AccountDropdownMenu
                  anchor="bottom end"
                  signingOut={signingOut}
                  onSignOut={handleSignOut}
                />
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
              on a stable h-14 header. The version stamp tucks under the
              wordmark so a fresh deploy is visible at a glance. */}
          <SidebarHeader>
            <div className="flex items-center gap-2.5 px-2 py-1.5">
              <ScannerMark className="size-7 text-foreground" />
              <div className="flex min-w-0 flex-col">
                <div className="flex items-center gap-1.5 text-xs leading-snug font-semibold tracking-[0.14em] text-foreground uppercase">
                  <span className="truncate">Research Intelligence</span>
                  {/* Names the area so it is obvious which tool you are in —
                      the reading app and the Studio share this chrome. */}
                  {areaBadge && (
                    <span className="shrink-0 rounded-sm bg-accent px-1.5 py-px text-[10px] tracking-[0.12em] text-white">
                      {areaBadge}
                    </span>
                  )}
                </div>
                <VersionStamp />
              </div>
            </div>
          </SidebarHeader>

          <SidebarBody>
            <SidebarSection>
              {nav.map(({ href, label, Icon, exact }) => (
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
                <AccountDropdownMenu
                  anchor="top start"
                  signingOut={signingOut}
                  onSignOut={handleSignOut}
                />
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

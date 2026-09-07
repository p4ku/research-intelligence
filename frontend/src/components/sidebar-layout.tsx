'use client'

import { useT } from '@/lib/i18n-client'
import * as Headless from '@headlessui/react'
import clsx from 'clsx'
import React, { useState } from 'react'
import { NavbarItem } from './app-navbar'

/**
 * Canvas mode. A page that puts `data-canvas` on its root asks the shell for
 * the viewport: the document stops scrolling, the card's padding and chrome
 * go, and the page is stretched to fill main edge to edge. The page then owns
 * its scroll regions (the Ask transcript) with plain flex — no
 * `calc(100dvh - <the shell's padding>)` arithmetic that drifts the moment
 * the shell changes. Pages without the attribute are untouched.
 */
const CANVAS_ROOT = 'has-[[data-canvas]]:h-dvh has-[[data-canvas]]:overflow-hidden'
const CANVAS_MAIN = 'has-[[data-canvas]]:min-h-0 has-[[data-canvas]]:max-lg:px-2'
const CANVAS_CARD =
  'has-[[data-canvas]]:flex has-[[data-canvas]]:min-h-0 has-[[data-canvas]]:flex-col has-[[data-canvas]]:p-0 has-[[data-canvas]]:lg:bg-transparent has-[[data-canvas]]:lg:shadow-none has-[[data-canvas]]:lg:ring-0'
const CANVAS_WRAP =
  'has-[[data-canvas]]:flex has-[[data-canvas]]:min-h-0 has-[[data-canvas]]:w-full has-[[data-canvas]]:max-w-none has-[[data-canvas]]:flex-1 has-[[data-canvas]]:flex-col'

function OpenMenuIcon() {
  return (
    <svg data-slot="icon" viewBox="0 0 20 20" aria-hidden="true">
      <path d="M2 6.75C2 6.33579 2.33579 6 2.75 6H17.25C17.6642 6 18 6.33579 18 6.75C18 7.16421 17.6642 7.5 17.25 7.5H2.75C2.33579 7.5 2 7.16421 2 6.75ZM2 13.25C2 12.8358 2.33579 12.5 2.75 12.5H17.25C17.6642 12.5 18 12.8358 18 13.25C18 13.6642 17.6642 14 17.25 14H2.75C2.33579 14 2 13.6642 2 13.25Z" />
    </svg>
  )
}

function CloseMenuIcon() {
  return (
    <svg data-slot="icon" viewBox="0 0 20 20" aria-hidden="true">
      <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
    </svg>
  )
}

function MobileSidebar({
  open,
  close,
  children,
}: React.PropsWithChildren<{ open: boolean; close: () => void }>) {
  const t = useT()
  // The close button was named but the dialog itself was not, so it announced
  // as an unnamed dialog on open.
  return (
    <Headless.Dialog open={open} onClose={close} aria-label={t('Navigation')} className="lg:hidden">
      <Headless.DialogBackdrop
        transition
        className="fixed inset-0 bg-black/30 transition data-enter:duration-300 data-enter:ease-out data-leave:duration-200 data-leave:ease-in data-closed:opacity-0"
      />
      <Headless.DialogPanel
        transition
        className="fixed inset-y-0 w-full max-w-80 p-2 transition duration-300 ease-in-out data-closed:-translate-x-full"
      >
        <div className="flex h-full flex-col rounded-lg bg-surface shadow-xs ring-1 ring-line">
          <div className="-mb-3 px-4 pt-3">
            <Headless.CloseButton as={NavbarItem} aria-label={t('Close navigation')}>
              <CloseMenuIcon />
            </Headless.CloseButton>
          </div>
          {children}
        </div>
      </Headless.DialogPanel>
    </Headless.Dialog>
  )
}

export function SidebarLayout({
  navbar,
  sidebar,
  children,
}: React.PropsWithChildren<{ navbar: React.ReactNode; sidebar: React.ReactNode }>) {
  let [showSidebar, setShowSidebar] = useState(false)
  const t = useT()

  return (
    <div
      className={clsx(
        'relative isolate flex min-h-svh w-full bg-surface max-lg:flex-col lg:bg-background',
        CANVAS_ROOT,
      )}
    >
      {/* Sidebar on desktop */}
      <div className="fixed inset-y-0 left-0 w-64 max-lg:hidden">{sidebar}</div>

      {/* Sidebar on mobile */}
      <MobileSidebar open={showSidebar} close={() => setShowSidebar(false)}>
        {sidebar}
      </MobileSidebar>

      {/* Navbar on mobile */}
      <header className="flex items-center px-4 lg:hidden">
        <div className="py-2.5">
          <NavbarItem onClick={() => setShowSidebar(true)} aria-label={t('Open navigation')}>
            <OpenMenuIcon />
          </NavbarItem>
        </div>
        <div className="min-w-0 flex-1">{navbar}</div>
      </header>

      {/* Content */}
      <main
        className={clsx(
          'flex flex-1 flex-col pb-2 lg:min-w-0 lg:pt-2 lg:pr-2 lg:pl-64',
          CANVAS_MAIN,
        )}
      >
        <div
          className={clsx(
            'grow p-6 lg:rounded-lg lg:bg-surface lg:p-10 lg:shadow-xs lg:ring-1 lg:ring-line',
            CANVAS_CARD,
          )}
        >
          <div className={clsx('mx-auto max-w-6xl', CANVAS_WRAP)}>{children}</div>
        </div>
      </main>
    </div>
  )
}
